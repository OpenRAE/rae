"""Issue #601: libvirt driver adapter behavior."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
from raes_backend_libvirt.cloudinit import CloudInitSpec, CloudInitUser
from raes_backend_libvirt.driver import DomainSpec, NetworkAcl, NetworkSpec
from raes_backend_libvirt.drivers.libvirt import LibvirtDeploymentDriver, _raes_uuid
from raes_backend_protocols.naming import provider_resource_name

# Real libvirt reports a missing object with these stable VIR_ERR_NO_* codes via
# libvirtError.get_error_code(); VIR_ERR_OPERATION_INVALID is raised by destroy()
# on an inactive object; anything else (e.g. an internal error) is a real failure.
# The fake mirrors that contract so tests exercise the driver's genuine
# absence-vs-error classification rather than a Python KeyError artifact.
_VIR_ERR_INTERNAL_ERROR = 1
_VIR_ERR_NO_DOMAIN = 42
_VIR_ERR_NO_NETWORK = 43
_VIR_ERR_OPERATION_INVALID = 55
_VIR_ERR_NO_NWFILTER = 62


def _runtime_name(address: str) -> str:
    return provider_resource_name(address, prefix="raes-test")


def _seed_dir(workspace: Path, address: str = "provision.node.web") -> Path:
    return workspace / _runtime_name(address)


class _FakeLibvirtError(Exception):
    """Stand-in for ``libvirt.libvirtError`` exposing ``get_error_code()``."""

    def __init__(self, code: int) -> None:
        super().__init__(f"libvirt error {code}")
        self._code = code

    def get_error_code(self) -> int:
        return self._code


@pytest.fixture(autouse=True)
def _install_fake_libvirt_error_type(monkeypatch: pytest.MonkeyPatch) -> None:
    libvirt = ModuleType("libvirt")
    libvirt.libvirtError = _FakeLibvirtError
    monkeypatch.setitem(sys.modules, "libvirt", libvirt)


def _xml_attr(xml: str, attr: str) -> str:
    match = re.search(rf'{attr}="([^"]+)"', xml)
    return match.group(1) if match else ""


class _NativeObject:
    def __init__(self, uuid: str = "", *, fail_create: bool = False, fail_destroy_code: int | None = None) -> None:
        self.uuid = uuid
        self.fail_create = fail_create
        self.fail_destroy_code = fail_destroy_code
        self.created = False
        self.destroyed = False
        self.undefined = False

    def create(self):
        if self.fail_create:
            raise RuntimeError("native start failure with /secret/path and TOKEN")
        self.created = True

    def destroy(self):
        if self.fail_destroy_code is not None:
            raise _FakeLibvirtError(self.fail_destroy_code)
        self.destroyed = True

    def undefine(self):
        self.undefined = True

    def UUIDString(self):  # noqa: N802 - mirrors libvirt API
        return self.uuid

    def isActive(self):  # noqa: N802 - mirrors libvirt API
        return int(self.created and not self.destroyed)


class _FakeConnection:
    def __init__(self, *, fail_define: bool = False, fail_create: bool = False) -> None:
        self.fail_define = fail_define
        self.fail_create = fail_create
        self.network_xml: list[str] = []
        self.domain_xml: list[str] = []
        self.nwfilter_xml: list[str] = []
        self.networks: dict[str, _NativeObject] = {}
        self.domains: dict[str, _NativeObject] = {}
        self.nwfilters: dict[str, _NativeObject] = {}

    def nwfilterDefineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        self.nwfilter_xml.append(xml)
        native = _NativeObject(_uuid_from_xml(xml))
        self.nwfilters[_xml_attr(xml, "name")] = native
        return native

    def nwfilterLookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
        try:
            return self.nwfilters[name]
        except KeyError:
            raise _FakeLibvirtError(_VIR_ERR_NO_NWFILTER) from None

    def networkDefineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        if self.fail_define:
            raise RuntimeError("native failure with /secret/path and TOKEN")
        self.network_xml.append(xml)
        native = _NativeObject(_uuid_from_xml(xml), fail_create=self.fail_create)
        self.networks[_name_from_xml(xml)] = native
        return native

    def defineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        if self.fail_define:
            raise RuntimeError("native failure with /secret/path and TOKEN")
        self.domain_xml.append(xml)
        native = _NativeObject(_uuid_from_xml(xml), fail_create=self.fail_create)
        self.domains[_name_from_xml(xml)] = native
        return native

    def networkLookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
        try:
            return self.networks[name]
        except KeyError:
            raise _FakeLibvirtError(_VIR_ERR_NO_NETWORK) from None

    def lookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
        try:
            return self.domains[name]
        except KeyError:
            raise _FakeLibvirtError(_VIR_ERR_NO_DOMAIN) from None


def _name_from_xml(xml: str) -> str:
    start = xml.index("<name>") + len("<name>")
    end = xml.index("</name>")
    return xml[start:end]


def _uuid_from_xml(xml: str) -> str:
    match = re.search(r"<uuid>([^<]+)</uuid>", xml)
    return match.group(1) if match else ""


def test_libvirt_driver_realize_defines_networks_and_domains_with_safe_names(monkeypatch):
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")

    def unexpected_readback(*_args, **_kwargs):
        pytest.fail("realization must not collect an unrequested substrate observation")

    monkeypatch.setattr(driver, "_compute_substrate_observation", unexpected_readback)

    result = driver.realize(
        networks=(NetworkSpec(address="provision.network.lan", name="lan<>"),),
        domains=(
            DomainSpec(
                address="provision.node.web",
                name="web/vm",
                image_ref="/var/lib/libvirt/images/base.qcow2",
                memory_mib=1024,
                vcpus=2,
                networks=("provision.network.lan",),
            ),
        ),
    )

    assert not result.diagnostics
    assert result.observations == ()
    network_name = _runtime_name("provision.network.lan")
    domain_name = _runtime_name("provision.node.web")
    assert network_name in connection.network_xml[0]
    assert domain_name in connection.domain_xml[0]
    assert "lan<>" not in connection.network_xml[0]
    assert "web/vm" not in connection.domain_xml[0]
    assert f'source network="{network_name}"' in connection.domain_xml[0]
    assert driver.realized_addresses() == frozenset({"provision.network.lan", "provision.node.web"})


def test_libvirt_driver_diagnostics_do_not_leak_native_exception_or_image_path():
    connection = _FakeConnection(fail_define=True)
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")

    result = driver.realize(
        networks=(),
        domains=(
            DomainSpec(
                address="provision.node.web",
                name="web",
                image_ref="/secret/path/base.qcow2",
                memory_mib=512,
                vcpus=1,
            ),
        ),
    )

    assert result.diagnostics
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "libvirt-backend.driver.operation-failed"
    assert "/secret/path" not in diagnostic.message
    assert "TOKEN" not in diagnostic.message
    assert "provision.node.web" in diagnostic.message


class _FakeSeedBuilder:
    def __init__(self) -> None:
        self.seed_dirs: list[Path] = []

    def build(self, *, seed_dir: Path) -> Path:
        seed = seed_dir / "seed.iso"
        seed.write_bytes(b"cidata")
        self.seed_dirs.append(seed_dir)
        return seed


def test_libvirt_driver_realizes_cloud_init_seed_as_readonly_cdrom(tmp_path):
    connection = _FakeConnection()
    seed_builder = _FakeSeedBuilder()
    driver = LibvirtDeploymentDriver(
        connection=connection,
        name_prefix="raes-test",
        workspace=tmp_path,
        seed_builder=seed_builder,
    )

    result = driver.realize(
        networks=(),
        domains=(
            DomainSpec(
                address="provision.node.web",
                name="web",
                image_ref="/img/base.qcow2",
                cloud_init=CloudInitSpec(hostname="web", users=(CloudInitUser(name="alice"),)),
            ),
        ),
    )

    assert not result.diagnostics
    seed_dir = _seed_dir(tmp_path)
    assert (seed_dir / "user-data").read_text().startswith("#cloud-config")
    assert (seed_dir / "meta-data").exists()
    assert seed_builder.seed_dirs == [seed_dir]
    domain_xml = connection.domain_xml[0]
    assert 'device="cdrom"' in domain_xml
    assert str(seed_dir / "seed.iso") in domain_xml
    assert "<readonly" in domain_xml


def _realize_seed_domain(driver):
    return driver.realize(
        networks=(),
        domains=(
            DomainSpec(
                address="provision.node.web",
                name="web",
                image_ref=None,
                cloud_init=CloudInitSpec(hostname="web", users=(CloudInitUser(name="alice"),)),
            ),
        ),
    )


def test_libvirt_seed_artifacts_use_private_modes(tmp_path):
    driver = LibvirtDeploymentDriver(
        connection=_FakeConnection(),
        name_prefix="raes-test",
        workspace=tmp_path,
        seed_builder=_FakeSeedBuilder(),
    )

    _realize_seed_domain(driver)

    seed_dir = _seed_dir(tmp_path)
    # Directories are traversable (so the QEMU process can reach the attached ISO)
    # but not listable; the rendered source files stay 0o600-private.
    assert seed_dir.stat().st_mode & 0o777 == 0o711
    assert tmp_path.stat().st_mode & 0o777 == 0o711
    assert (seed_dir / "user-data").stat().st_mode & 0o777 == 0o600
    assert (seed_dir / "meta-data").stat().st_mode & 0o777 == 0o600


def test_libvirt_seed_write_neutralizes_pre_positioned_symlink(tmp_path):
    # A pre-positioned symlink where user-data would be written must never be
    # followed: the stale entry is cleared (target untouched) and the seed is
    # created fresh inside an owner-private directory, so re-apply still succeeds.
    seed_dir = _seed_dir(tmp_path)
    seed_dir.mkdir(parents=True)
    target = tmp_path / "victim"
    target.write_text("original")
    (seed_dir / "user-data").symlink_to(target)
    driver = LibvirtDeploymentDriver(
        connection=_FakeConnection(),
        name_prefix="raes-test",
        workspace=tmp_path,
        seed_builder=_FakeSeedBuilder(),
    )

    result = _realize_seed_domain(driver)

    assert not result.diagnostics
    assert target.read_text() == "original"  # the symlink target was never written through
    user_data = seed_dir / "user-data"
    assert not user_data.is_symlink()
    assert user_data.read_text().startswith("#cloud-config")
    assert user_data.stat().st_mode & 0o777 == 0o600


def test_libvirt_seed_write_clears_stale_seed_dir_for_clean_reapply(tmp_path):
    # A leftover seed directory from a crashed prior apply is replaced wholesale,
    # so exclusive (O_EXCL) creation of the new seed files never collides.
    seed_dir = _seed_dir(tmp_path)
    seed_dir.mkdir(parents=True)
    (seed_dir / "user-data").write_text("stale")
    (seed_dir / "leftover").write_text("debris")
    driver = LibvirtDeploymentDriver(
        connection=_FakeConnection(),
        name_prefix="raes-test",
        workspace=tmp_path,
        seed_builder=_FakeSeedBuilder(),
    )

    result = _realize_seed_domain(driver)

    assert not result.diagnostics
    assert not (seed_dir / "leftover").exists()
    assert (seed_dir / "user-data").read_text().startswith("#cloud-config")


def test_libvirt_driver_destroy_cleans_up_seed_media(tmp_path):
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(
        connection=connection,
        name_prefix="raes-test",
        workspace=tmp_path,
        seed_builder=_FakeSeedBuilder(),
    )
    driver.realize(
        networks=(),
        domains=(
            DomainSpec(
                address="provision.node.web",
                name="web",
                image_ref=None,
                cloud_init=CloudInitSpec(hostname="web", users=(CloudInitUser(name="alice"),)),
            ),
        ),
    )
    seed_dir = _seed_dir(tmp_path)
    assert seed_dir.exists()

    driver.destroy(networks=(), domains=("provision.node.web",))

    assert not seed_dir.exists()


def test_libvirt_driver_converges_existing_objects_without_duplicating(tmp_path):
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test", seed_builder=_FakeSeedBuilder())
    specs = dict(
        networks=(NetworkSpec(address="provision.network.lan", name="lan"),),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),),
    )

    first = driver.realize(**specs)
    prior_domain = connection.domains[_runtime_name("provision.node.web")]
    prior_network = connection.networks[_runtime_name("provision.network.lan")]
    second = driver.realize(**specs)

    assert not first.diagnostics and not second.diagnostics
    # Re-apply converges: the prior objects are stopped and undefined, then the
    # desired state is redefined — so each name resolves to exactly one object
    # (no duplicate) and the new definition genuinely takes effect.
    assert prior_domain.destroyed and prior_domain.undefined
    assert prior_network.destroyed and prior_network.undefined
    assert len(connection.domains) == 1
    assert len(connection.networks) == 1
    assert len(connection.domain_xml) == 2
    assert second.domains[0].realized is True


def test_libvirt_convergence_refuses_to_replace_a_foreign_object(tmp_path):
    # A pre-existing object that shares the runtime name but is NOT the RAES object
    # for this address (different/unknown UUID) must never be destroyed: apply fails
    # closed with an ownership-conflict diagnostic and the foreign object survives.
    connection = _FakeConnection()
    foreign = _NativeObject(uuid="11111111-2222-3333-4444-555555555555")
    connection.domains[_runtime_name("provision.node.web")] = foreign
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test", seed_builder=_FakeSeedBuilder())

    result = driver.realize(
        networks=(),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),),
    )

    assert [d.code for d in result.diagnostics] == ["libvirt-backend.driver.ownership-conflict"]
    assert not foreign.destroyed and not foreign.undefined
    assert connection.domains[_runtime_name("provision.node.web")] is foreign  # never replaced
    assert connection.domain_xml == []  # nothing redefined


def test_libvirt_convergence_fails_closed_when_stopping_owned_object_fails():
    # Issue #604 (codex post-push finding): convergence stops an owned object
    # before undefining/redefining it. A stop that fails for a non-benign reason
    # (permission/internal) must NOT be suppressed-then-undefined — the apply fails
    # closed and the still-running owned domain is left intact for retry.
    connection = _FakeConnection()
    existing = _NativeObject(uuid=_raes_uuid("provision.node.web"), fail_destroy_code=_VIR_ERR_INTERNAL_ERROR)
    connection.domains[_runtime_name("provision.node.web")] = existing
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test", seed_builder=_FakeSeedBuilder())

    result = driver.realize(
        networks=(), domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),)
    )

    assert [d.code for d in result.diagnostics] == ["libvirt-backend.driver.operation-failed"]
    assert existing.undefined is False  # never undefined a domain we could not stop
    assert driver.realized_addresses() == frozenset()


def test_libvirt_convergence_tolerates_stopping_an_inactive_owned_object():
    # The benign side of the same path: converging an owned object that is already
    # inactive (stop raises VIR_ERR_OPERATION_INVALID) still undefines + redefines.
    connection = _FakeConnection()
    existing = _NativeObject(uuid=_raes_uuid("provision.node.web"), fail_destroy_code=_VIR_ERR_OPERATION_INVALID)
    connection.domains[_runtime_name("provision.node.web")] = existing
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test", seed_builder=_FakeSeedBuilder())

    result = driver.realize(
        networks=(), domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),)
    )

    assert not result.diagnostics
    assert existing.undefined is True  # inactive object converged (undefined) then redefined
    assert driver.realized_addresses() == {"provision.node.web"}


def test_libvirt_domain_xml_carries_stable_raes_ownership_uuid():
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test", seed_builder=_FakeSeedBuilder())

    first = driver.realize(networks=(), domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),))
    uuid_first = _uuid_from_xml(connection.domain_xml[0])

    # Re-realizing the same address reproduces the same UUID (proves ownership);
    # a different address would derive a different UUID.
    driver.realize(networks=(), domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),))
    uuid_second = _uuid_from_xml(connection.domain_xml[1])

    assert not first.diagnostics
    assert _raes_uuid("provision.node.web") == "19837e5e-7699-51af-8bd1-435e6ce85a5f"
    assert uuid_first and uuid_first == uuid_second


def test_libvirt_network_xml_realizes_cidr_into_ip_and_dhcp_range():
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")

    driver.realize(
        networks=(
            NetworkSpec(
                address="provision.network.lan",
                name="lan",
                cidr="192.168.50.0/24",
                gateway="192.168.50.1",
            ),
        ),
        domains=(),
    )

    network_xml = connection.network_xml[0]
    assert 'address="192.168.50.1"' in network_xml
    assert 'netmask="255.255.255.0"' in network_xml
    assert 'start="192.168.50.2"' in network_xml
    assert 'end="192.168.50.254"' in network_xml


def test_libvirt_driver_realizes_network_acls_as_nwfilter(tmp_path):
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    acl = NetworkAcl(
        name="allow-http",
        action="accept",
        direction="in",
        protocol="tcp",
        src_cidr="10.0.0.0/24",
        dst_cidr="192.168.1.0/24",
        ports=(80,),
    )

    driver.realize(
        networks=(),
        domains=(
            DomainSpec(
                address="provision.node.web",
                name="web",
                image_ref=None,
                networks=("provision.network.lan",),
                network_acls=(acl,),
            ),
        ),
    )

    nwfilter_xml = connection.nwfilter_xml[0]
    filter_name = _xml_attr(nwfilter_xml, "name")
    assert nwfilter_xml.startswith(f'<filter name="{filter_name}" chain="root">')
    assert '<rule action="accept" direction="in"' in nwfilter_xml
    assert "<tcp " in nwfilter_xml
    assert 'srcipaddr="10.0.0.0"' in nwfilter_xml
    assert 'srcipmask="255.255.255.0"' in nwfilter_xml
    assert 'dstipaddr="192.168.1.0"' in nwfilter_xml
    assert 'dstportstart="80"' in nwfilter_xml
    # The domain interface references the nwfilter so the host enforces the ACL.
    assert f'<filterref filter="{filter_name}"' in connection.domain_xml[0]


def test_libvirt_reapply_enforces_tightened_acl_via_redefined_nwfilter(tmp_path):
    # A re-apply that tightens an ACL (allow -> deny) must redefine the nwfilter so
    # the new rule is genuinely enforced, not recorded-but-skipped behind a stale
    # filter the host still applies.
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    allow = NetworkAcl(name="allow-http", action="accept", direction="in", protocol="tcp", ports=(80,))
    deny = NetworkAcl(name="deny-http", action="drop", direction="in", protocol="tcp", ports=(80,))

    driver.realize(
        networks=(),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None, network_acls=(allow,)),),
    )
    second = driver.realize(
        networks=(),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None, network_acls=(deny,)),),
    )

    assert not second.diagnostics
    # The filter was redefined (two define calls) and the live definition is the
    # tightened deny rule, with no lingering accept rule.
    assert len(connection.nwfilter_xml) == 2
    assert '<rule action="drop" direction="in"' in connection.nwfilter_xml[1]
    assert "accept" not in connection.nwfilter_xml[1]


def test_libvirt_driver_destroy_undefines_nwfilter(tmp_path):
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    acl = NetworkAcl(name="deny", action="drop", direction="inout", protocol="all")
    driver.realize(
        networks=(),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None, network_acls=(acl,)),),
    )
    filter_name = _xml_attr(connection.nwfilter_xml[0], "name")
    assert filter_name in connection.nwfilters

    driver.destroy(networks=(), domains=("provision.node.web",))

    assert connection.nwfilters[filter_name].undefined is True


def test_libvirt_nwfilter_define_refuses_to_overwrite_a_foreign_filter():
    # An ACL whose runtime filter name collides with a pre-existing, non-RAES
    # filter must not redefine it: apply fails closed and the foreign filter is
    # left untouched (no redefine), so other domains' filtering is not weakened.
    connection = _FakeConnection()
    foreign = _NativeObject(uuid="99999999-8888-7777-6666-555555555555")
    filter_name = f"{_runtime_name('provision.node.web')}-acl"
    connection.nwfilters[filter_name] = foreign
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    acl = NetworkAcl(name="allow-all", action="accept", direction="inout", protocol="all")

    result = driver.realize(
        networks=(),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None, network_acls=(acl,)),),
    )

    assert [d.code for d in result.diagnostics] == ["libvirt-backend.driver.ownership-conflict"]
    assert connection.nwfilter_xml == []  # the foreign filter was never redefined
    assert connection.nwfilters[filter_name] is foreign


def test_libvirt_nwfilter_define_fails_closed_on_a_mismatched_absence_code():
    class _MismatchedAbsenceConnection(_FakeConnection):
        def nwfilterLookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
            del name
            raise _FakeLibvirtError(_VIR_ERR_NO_DOMAIN)

    connection = _MismatchedAbsenceConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    acl = NetworkAcl(name="allow-all", action="accept", direction="inout", protocol="all")

    result = driver.realize(
        networks=(),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None, network_acls=(acl,)),),
    )

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.driver.operation-failed"]
    assert connection.nwfilter_xml == []
    assert connection.domain_xml == []


def test_libvirt_domain_convergence_fails_closed_on_a_mismatched_absence_code():
    class _MismatchedAbsenceConnection(_FakeConnection):
        def lookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
            del name
            raise _FakeLibvirtError(_VIR_ERR_NO_NETWORK)

    connection = _MismatchedAbsenceConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")

    result = driver.realize(
        networks=(),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),),
    )

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.driver.operation-failed"]
    assert connection.domain_xml == []


def test_libvirt_nwfilter_cleanup_preserves_retry_state_on_a_mismatched_absence_code():
    class _MismatchedAbsenceConnection(_FakeConnection):
        def nwfilterLookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
            del name
            raise _FakeLibvirtError(_VIR_ERR_NO_DOMAIN)

    address = "provision.node.web"
    connection = _MismatchedAbsenceConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    driver._filters[address] = "raes-test-web-acl"

    driver._undefine_nwfilter(connection, address)

    assert driver._filters[address] == "raes-test-web-acl"


def test_libvirt_destroy_refuses_to_remove_a_foreign_object():
    # A DELETE whose runtime name collides with a foreign object must not destroy
    # it: the ownership guard applies to deletion, not just convergence.
    connection = _FakeConnection()
    foreign = _NativeObject(uuid="11111111-2222-3333-4444-555555555555")
    connection.domains[_runtime_name("provision.node.web")] = foreign
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")

    result = driver.destroy(networks=(), domains=("provision.node.web",))

    assert [d.code for d in result.diagnostics] == ["libvirt-backend.driver.ownership-conflict"]
    assert not foreign.destroyed and not foreign.undefined
    assert connection.domains[_runtime_name("provision.node.web")] is foreign


def test_libvirt_driver_destroy_uses_previously_realized_names():
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    driver.realize(
        networks=(NetworkSpec(address="provision.network.lan", name="lan"),),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),),
    )

    result = driver.destroy(networks=("provision.network.lan",), domains=("provision.node.web",))

    assert not result.diagnostics
    network = connection.networks[_runtime_name("provision.network.lan")]
    domain = connection.domains[_runtime_name("provision.node.web")]
    assert network.destroyed is True
    assert network.undefined is True
    assert domain.destroyed is True
    assert domain.undefined is True
    assert driver.realized_addresses() == frozenset()


def test_libvirt_driver_teardown_of_absent_domain_is_idempotent_success():
    # Issue #604: a DELETE for a domain whose native object is already absent
    # (never realized, or torn down by a prior run) succeeds as "not realized"
    # with no diagnostic — teardown is idempotent, not a hard failure.
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")

    result = driver.destroy(networks=(), domains=("provision.node.web",))

    assert not result.diagnostics
    assert [handle.realized for handle in result.domains] == [False]


def test_libvirt_driver_teardown_of_absent_network_is_idempotent_success():
    # Issue #604: same idempotent-absence contract for networks.
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")

    result = driver.destroy(networks=("provision.network.lan",), domains=())

    assert not result.diagnostics
    assert [handle.realized for handle in result.networks] == [False]


def test_libvirt_driver_observes_owned_domain_without_redefining_it():
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    domain = DomainSpec(address="provision.node.web", name="web", image_ref=None)
    assert not driver.realize(networks=(), domains=(domain,)).diagnostics
    definitions_before = tuple(connection.domain_xml)

    result = driver.observe(domains=(domain,))

    assert not result.diagnostics
    assert [item.address for item in result.observations] == [domain.address]
    assert tuple(connection.domain_xml) == definitions_before


def test_libvirt_driver_observe_rejects_inactive_domain():
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    domain = DomainSpec(address="provision.node.web", name="web", image_ref=None)
    assert not driver.realize(networks=(), domains=(domain,)).diagnostics
    connection.domains[_runtime_name(domain.address)].destroy()

    result = driver.observe(domains=(domain,))

    assert [item.code for item in result.diagnostics] == ["libvirt-backend.driver.operation-failed"]
    assert result.observations == ()


def test_libvirt_driver_teardown_is_idempotent_across_repeated_realize_and_destroy():
    # Issue #604: realize -> destroy -> destroy again. The second destroy sees an
    # absent object and still succeeds; the snapshot/realized set stays consistent.
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test", seed_builder=_FakeSeedBuilder())
    specs = dict(
        networks=(NetworkSpec(address="provision.network.lan", name="lan"),),
        domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),),
    )
    driver.realize(**specs)
    # The fake keeps torn-down objects in its dict, so model real removal here to
    # prove idempotence against a genuinely-absent second lookup.
    connection.domains.clear()
    connection.networks.clear()

    first = driver.destroy(networks=("provision.network.lan",), domains=("provision.node.web",))
    second = driver.destroy(networks=("provision.network.lan",), domains=("provision.node.web",))

    assert not first.diagnostics
    assert not second.diagnostics
    assert all(not handle.realized for handle in (*second.networks, *second.domains))
    assert driver.realized_addresses() == frozenset()


def test_libvirt_driver_teardown_fails_closed_on_non_absence_lookup_error():
    # Issue #604 guardrail: absence is idempotent, but a connection/permission/
    # internal lookup error is NOT — it stays a diagnostic and preserves the
    # object as still-realized so the snapshot is kept for retry.
    class _ConnectionThatFailsLookup:
        def lookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
            raise _FakeLibvirtError(_VIR_ERR_INTERNAL_ERROR)

        def networkLookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
            raise _FakeLibvirtError(_VIR_ERR_INTERNAL_ERROR)

    driver = LibvirtDeploymentDriver(connection=_ConnectionThatFailsLookup(), name_prefix="raes-test")

    result = driver.destroy(networks=(), domains=("provision.node.web",))

    assert [d.code for d in result.diagnostics] == ["libvirt-backend.driver.operation-failed"]
    assert [handle.realized for handle in result.domains] == [True]


def test_libvirt_driver_realize_rolls_back_partially_defined_domain_on_create_failure(tmp_path):
    # Issue #604: if defineXML succeeds but native.create() fails, the domain is
    # defined in libvirt but never started. Realize must roll it back — undefining
    # the definition and clearing its seed media — so a partial CREATE leaves no
    # orphaned domain or network behind.
    connection = _FakeConnection(fail_create=True)
    driver = LibvirtDeploymentDriver(
        connection=connection,
        name_prefix="raes-test",
        workspace=tmp_path,
        seed_builder=_FakeSeedBuilder(),
    )

    result = driver.realize(
        networks=(),
        domains=(
            DomainSpec(
                address="provision.node.web",
                name="web",
                image_ref=None,
                cloud_init=CloudInitSpec(hostname="web", users=(CloudInitUser(name="alice"),)),
            ),
        ),
    )

    assert [d.code for d in result.diagnostics] == ["libvirt-backend.driver.operation-failed"]
    # The just-defined domain was undefined (rolled back), not left orphaned.
    defined = connection.domains[_runtime_name("provision.node.web")]
    assert defined.undefined is True
    # Its private seed media was cleaned up too.
    assert not _seed_dir(tmp_path).exists()
    assert driver.realized_addresses() == frozenset()


def test_libvirt_realize_rollback_leaves_a_pre_existing_updated_object_intact():
    # Issue #604 (codex finding 1): the driver sees both CREATE and UPDATE specs
    # without an action, so rollback must not tear down a pre-existing resource an
    # UPDATE converged. Here an UPDATE of an existing owned domain succeeds, then a
    # second (foreign-named) domain fails; the updated domain must survive so the
    # preserved baseline snapshot that still claims it realized stays truthful.
    connection = _FakeConnection()
    existing = _NativeObject(uuid=_raes_uuid("provision.node.web"))
    connection.domains[_runtime_name("provision.node.web")] = existing
    foreign = _NativeObject(uuid="11111111-2222-3333-4444-555555555555")
    connection.domains[_runtime_name("provision.node.other")] = foreign
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test", seed_builder=_FakeSeedBuilder())

    result = driver.realize(
        networks=(),
        domains=(
            DomainSpec(address="provision.node.web", name="web", image_ref=None),
            DomainSpec(address="provision.node.other", name="other", image_ref=None),
        ),
    )

    # The foreign collision fails the apply closed.
    assert [d.code for d in result.diagnostics] == ["libvirt-backend.driver.ownership-conflict"]
    # The updated domain's fresh definition is NOT rolled back (its snapshot entry
    # remains truthful); the foreign object is never touched.
    updated = connection.domains[_runtime_name("provision.node.web")]
    assert updated.created is True
    assert updated.undefined is False
    assert not foreign.destroyed and not foreign.undefined


def test_libvirt_driver_teardown_fails_closed_when_stop_fails_for_a_running_object():
    # Issue #604 (codex finding 2): a destroy() that fails for permission/internal
    # reasons must NOT be masked — the object may still be running, so teardown
    # fails closed (diagnostic + realized) and never undefines it, keeping the
    # snapshot entry for retry.
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    driver.realize(networks=(), domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),))
    runtime_name = _runtime_name("provision.node.web")
    connection.domains[runtime_name].fail_destroy_code = _VIR_ERR_INTERNAL_ERROR

    result = driver.destroy(networks=(), domains=("provision.node.web",))

    assert [d.code for d in result.diagnostics] == ["libvirt-backend.driver.operation-failed"]
    assert [handle.realized for handle in result.domains] == [True]
    assert connection.domains[runtime_name].undefined is False  # never undefined a still-running domain


def test_libvirt_driver_teardown_undefines_an_already_inactive_object():
    # Issue #604 (codex finding 2): stopping an object that is already inactive
    # (VIR_ERR_OPERATION_INVALID) is benign — teardown still undefines it and
    # succeeds.
    connection = _FakeConnection()
    driver = LibvirtDeploymentDriver(connection=connection, name_prefix="raes-test")
    driver.realize(networks=(), domains=(DomainSpec(address="provision.node.web", name="web", image_ref=None),))
    runtime_name = _runtime_name("provision.node.web")
    connection.domains[runtime_name].fail_destroy_code = _VIR_ERR_OPERATION_INVALID

    result = driver.destroy(networks=(), domains=("provision.node.web",))

    assert not result.diagnostics
    assert [handle.realized for handle in result.domains] == [False]
    assert connection.domains[runtime_name].undefined is True

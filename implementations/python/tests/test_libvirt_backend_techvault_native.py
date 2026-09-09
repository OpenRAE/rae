"""Native TechVault libvirt realization and live-gate coverage."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest
from libvirt_interface_fixtures import (
    HOSTILE_INTERFACE_CASES,
    QUOTED_ADDRESS_COMMAND,
    QUOTED_MAC_ARM,
    VALID_INTERFACE,
    domain_with_interface,
    domain_with_malformed_entry,
)
from paths import EXAMPLES_DIR
from raes import parse_sdl
from raes_backend_libvirt import create_libvirt_target
from raes_backend_libvirt.cloudinit import CloudInitSpec, CloudInitUser
from raes_backend_libvirt.driver import DomainSpec, NetworkAcl, NetworkSpec, ServiceSpec
from raes_backend_libvirt.envelopes import load_libvirt_realization_envelope
from raes_backend_libvirt.techvault_appliance import _init_script
from raes_backend_libvirt.techvault_native import (
    BusyboxInitramfsBuilder,
    ProbeResult,
    TechVaultNativeLibvirtDriver,
    check_native_readiness,
    expected_surface,
    native_soc_readback,
)
from raes_backend_protocols.naming import provider_resource_name
from raes_conformance.conformance.target_planning import target_probe_execution_plan
from raes_operations import techvault_live
from raes_operations.techvault_live import (
    TechVaultLiveConfig,
    validate_techvault_live,
    validate_techvault_live_manifest,
)
from raes_runtime.control_plane import RuntimeControlPlane


class _NativeObject:
    def __init__(self, name: str = "", xml: str = "") -> None:
        self._name = name
        self._xml = xml
        self.created = False
        self.destroyed = False
        self.undefined = False

    def name(self):
        return self._name

    def create(self):
        self.created = True

    def isActive(self):  # noqa: N802 - mirrors libvirt API
        return int(self.created and not self.destroyed)

    def XMLDesc(self, _flags=0):  # noqa: N802 - mirrors libvirt API
        return self._xml

    def UUIDString(self):  # noqa: N802 - mirrors libvirt API
        if not self._xml:
            return None
        return ET.fromstring(self._xml).findtext("uuid")  # noqa: S314 - test-generated XML

    def destroy(self):
        self.destroyed = True

    def undefine(self):
        self.undefined = True


class _RollbackFailObject(_NativeObject):
    def destroy(self):
        raise RuntimeError("rollback blocked")


class _FakeConnection:
    def __init__(self) -> None:
        self.network_xml: list[str] = []
        self.domain_xml: list[str] = []
        self.networks: dict[str, _NativeObject] = {}
        self.domains: dict[str, _NativeObject] = {}

    def networkDefineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        self.network_xml.append(xml)
        name = _name_from_xml(xml)
        native = _NativeObject(name, xml)
        self.networks[name] = native
        return native

    def defineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        self.domain_xml.append(xml)
        name = _name_from_xml(xml)
        native = _NativeObject(name, xml)
        self.domains[name] = native
        return native

    def networkLookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
        return self.networks[name]

    def lookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
        return self.domains[name]

    def listAllDomains(self):  # noqa: N802 - mirrors libvirt API
        return [native for native in self.domains.values() if not native.undefined]

    def listAllNetworks(self):  # noqa: N802 - mirrors libvirt API
        return [native for native in self.networks.values() if not native.undefined]


class _SecondDomainFailsConnection(_FakeConnection):
    def __init__(self, *, rollback_fails: bool = False) -> None:
        super().__init__()
        self._define_count = 0
        self.rollback_fails = rollback_fails

    def defineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        self._define_count += 1
        if self._define_count == 2:
            raise RuntimeError("second define failed")
        self.domain_xml.append(xml)
        name = _name_from_xml(xml)
        native_type = _RollbackFailObject if self.rollback_fails else _NativeObject
        native = native_type(name, xml)
        self.domains[name] = native
        return native


class _LookupFailure(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("native lookup failed")
        self.code = code

    def get_error_code(self):
        return self.code


class _FailingLookupConnection(_FakeConnection):
    def lookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
        del name
        raise _LookupFailure(1)

    def listAllDomains(self):  # noqa: N802 - mirrors libvirt API
        raise _LookupFailure(1)


class _InactiveDomainConnection(_FakeConnection):
    def defineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        native = super().defineXML(xml)
        native.isActive = lambda: 0  # type: ignore[method-assign]
        return native


class _SubstitutedInitrdConnection(_FakeConnection):
    def defineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        root = ET.fromstring(xml)  # noqa: S314 - test-generated XML
        root.find("./os/initrd").text = "/unbound/substitute.cpio.gz"
        return super().defineXML(ET.tostring(root, encoding="unicode"))


class _ExtraAttachmentConnection(_FakeConnection):
    def defineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        root = ET.fromstring(xml)  # noqa: S314 - test-generated XML
        devices = root.find("devices")
        interface = ET.SubElement(devices, "interface", {"type": "network"})
        ET.SubElement(interface, "source", {"network": "foreign-network"})
        return super().defineXML(ET.tostring(root, encoding="unicode"))


class _WrongForwardModeConnection(_FakeConnection):
    def networkDefineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        root = ET.fromstring(xml)  # noqa: S314 - test-generated XML
        root.find("forward").set("mode", "route")
        return super().networkDefineXML(ET.tostring(root, encoding="unicode"))


class _UnverifiableDomainCleanupConnection(_FakeConnection):
    def listAllDomains(self):  # noqa: N802 - mirrors libvirt API
        raise RuntimeError("listing unavailable")


class _Builder:
    def build(self, *, domain, target: Path):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"initramfs")
        return target


class _Probe:
    def ping(self, ip: str):
        return ProbeResult(True)

    def tcp(self, ip: str, port: int):
        return ProbeResult(True)


def _name_from_xml(xml: str) -> str:
    start = xml.index("<name>") + len("<name>")
    end = xml.index("</name>")
    return xml[start:end]


def _bounded_scenario(tmp_path: Path) -> Path:
    path = tmp_path / "bounded.sdl.yaml"
    path.write_text(
        """\
name: bounded
nodes:
  lab: {type: switch}
  demo:
    type: compute
    resources: {ram: 128 MiB, cpu: 1}
    services: []
infrastructure:
  lab:
    properties: {cidr: 192.0.2.0/24, gateway: 192.0.2.1, internal: true}
  demo:
    links: [lab]
""",
        encoding="utf-8",
    )
    return path


def _bounded_specs() -> tuple[NetworkSpec, DomainSpec]:
    network = NetworkSpec(
        address="provision.network.lab",
        name="lab",
        cidr="192.0.2.0/24",
        gateway="192.0.2.1",
        labels={"internal": "true"},
    )
    domain = DomainSpec(
        address="provision.node.demo",
        name="demo",
        image_ref=None,
        memory_mib=128,
        vcpus=2,
        networks=(network.address,),
    )
    return network, domain


def test_native_driver_rejects_missing_initramfs_toolchain_before_libvirt_io(tmp_path):
    connection = _FakeConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        initramfs_builder=BusyboxInitramfsBuilder(busybox_path=tmp_path / "missing-busybox"),
    )
    network, domain = _bounded_specs()

    result = driver.realize(networks=(network,), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "libvirt-backend.techvault-native.initramfs-toolchain-unavailable"
    ]
    assert connection.network_xml == []
    assert connection.domain_xml == []
    assert not driver.state_dir.exists()


def test_native_driver_rejects_missing_kernel_before_libvirt_io(tmp_path):
    connection = _FakeConnection()
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=tmp_path / "missing-kernel",
        initramfs_builder=_Builder(),
    )
    network, domain = _bounded_specs()

    result = driver.realize(networks=(network,), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "libvirt-backend.techvault-native.kernel-unavailable"
    ]
    assert connection.network_xml == []
    assert connection.domain_xml == []


def test_native_artifact_preflight_skips_boot_toolchain_for_network_only_plan(tmp_path: Path) -> None:
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=_FakeConnection(),
        kernel_path=None,
        initramfs_builder=object(),
    )

    assert driver._artifact_preflight_diagnostics(()) == []


def test_native_artifact_preflight_normalizes_builder_exception(tmp_path: Path) -> None:
    class _ExplodingPreflightBuilder:
        def preflight(self) -> object:
            raise RuntimeError("host-specific toolchain detail")

    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=_FakeConnection(),
        kernel_path=kernel,
        initramfs_builder=_ExplodingPreflightBuilder(),
    )
    _network, domain = _bounded_specs()

    diagnostics = driver._artifact_preflight_diagnostics((domain,))

    assert [diagnostic.code for diagnostic in diagnostics] == [
        "libvirt-backend.techvault-native.initramfs-toolchain-unavailable"
    ]


def test_native_driver_normalizes_connection_failure(tmp_path: Path) -> None:
    def unavailable_connector(_uri: str) -> object:
        raise RuntimeError("host-specific connection detail")

    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connector=unavailable_connector,
        kernel_path=kernel,
        initramfs_builder=_Builder(),
    )
    network, domain = _bounded_specs()

    result = driver.realize(networks=(network,), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault-native.unavailable"]
    assert result.diagnostics[0].address == "runtime.libvirt.connection"


def _submit_native_scenario(path: Path, tmp_path: Path):
    connection = _FakeConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )
    target = create_libvirt_target(driver=driver, name_prefix="native-test")
    content = re.sub(r"(?m)^\s+os(?:_distribution|_version)?:.*\n", "", path.read_text(encoding="utf-8"))
    scenario = parse_sdl(content)
    execution_plan = target_probe_execution_plan(scenario, target, provisioning_only=True)
    # These tests exercise the native provisioning boundary itself. Planner
    # capability diagnostics for the same unsupported concerns are out of scope.
    execution_plan = replace(execution_plan, diagnostics=[])
    control_plane = RuntimeControlPlane(target)
    assert execution_plan.is_valid, execution_plan.diagnostics
    control_plane.register_planner_produced_plan(execution_plan)
    receipt = control_plane.submit_provisioning(execution_plan.provisioning)
    status = control_plane.get_operation(receipt.operation_id)
    return driver, connection, receipt, status, control_plane.snapshot


def test_operational_techvault_rejects_unrealized_concerns_before_libvirt_io(tmp_path):
    driver, connection, receipt, status, snapshot = _submit_native_scenario(
        EXAMPLES_DIR / "techvault-operational.sdl.yaml", tmp_path
    )

    assert receipt.accepted is True
    assert status is not None
    assert status.state.value == "failed"
    codes = {diagnostic.code for diagnostic in status.diagnostics}
    assert "libvirt-backend.techvault.resource-out-of-envelope" in codes
    assert "libvirt-backend.techvault.service-unsupported" in codes
    assert connection.domain_xml == []
    assert connection.network_xml == []
    assert driver.last_snapshot == {}
    assert snapshot.entries == {}


@pytest.mark.parametrize(
    ("filename", "domain_count", "network_count", "accepted"),
    (
        ("techvault-observability-core.sdl.yaml", 3, 1, True),
        ("techvault-defensive-min.sdl.yaml", 6, 1, False),
        ("techvault-enterprise-web.sdl.yaml", 9, 3, True),
        ("techvault-attacker-target.sdl.yaml", 8, 3, True),
    ),
)
def test_curated_variants_do_not_turn_planned_surfaces_into_native_claims(
    filename, domain_count, network_count, accepted, tmp_path
):
    del domain_count, network_count
    driver, connection, receipt, status, snapshot = _submit_native_scenario(EXAMPLES_DIR / filename, tmp_path)

    assert receipt.accepted is accepted
    if accepted:
        assert status is not None
        assert status.state.value == "failed"
    else:
        assert status is None
        assert [diagnostic.code for diagnostic in receipt.diagnostics] == ["realization.unsupported-exact-requirement"]
    assert connection.domain_xml == []
    assert connection.network_xml == []
    assert driver.last_snapshot == {}
    assert snapshot.entries == {}


def test_bounded_substrate_emits_complete_daemon_observations(tmp_path):
    connection = _FakeConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )
    network = NetworkSpec(
        address="provision.network.lab",
        name="lab",
        cidr="192.0.2.0/24",
        gateway="192.0.2.1",
        labels={"internal": "true"},
    )
    domain = DomainSpec(
        address="provision.node.demo",
        name="demo",
        image_ref=None,
        memory_mib=128,
        vcpus=2,
        networks=(network.address,),
    )

    result = driver.realize(networks=(network,), domains=(domain,))

    assert not result.diagnostics
    assert len(result.observations) == 14
    assert {observation.source.value for observation in result.observations} == {"daemon-observed"}
    substrate = next(
        observation for observation in result.observations if observation.concern.value == "compute-substrate"
    )
    assert substrate.value == "virtual-machine"
    assert substrate.binding_verified
    definitions_before = tuple(connection.domain_xml)
    readback = driver.observe(domains=(domain,))
    assert not readback.diagnostics
    assert [item.value for item in readback.observations] == ["virtual-machine"]
    assert tuple(connection.domain_xml) == definitions_before
    surface = expected_surface(driver.last_snapshot)
    assert surface["source"] == "daemon-observed"
    assert surface["domains"] == (provider_resource_name(domain.address, prefix="native-test"),)
    assert surface["networks"] == (provider_resource_name(network.address, prefix="native-test"),)
    assert "service_count" not in surface
    network_uuid = ET.fromstring(connection.network_xml[0]).findtext("uuid")  # noqa: S314 - test XML
    domain_uuid = ET.fromstring(connection.domain_xml[0]).findtext("uuid")  # noqa: S314 - test XML
    assert network_uuid
    assert domain_uuid
    assert network_uuid != domain_uuid
    binding = driver.last_snapshot["binding"]
    envelope = load_libvirt_realization_envelope("techvault-appliance")
    assert binding["driver"] == "techvault-appliance"
    assert binding["realization_envelope_digest"] == envelope.digest
    assert binding["configuration_digest"] == envelope.configuration.configuration_digest
    assert binding["driver_configuration_digest"].startswith("sha256:")
    assert set(binding["boot_artifact_digests"]) == {"kernel", "initramfs"}
    assert native_soc_readback(driver.last_snapshot) == {
        "status": "not-observed",
        "observation_source": "none",
        "reason": "guest SOC state requires concern-specific guest observation",
    }
    ready, readiness_diagnostics = check_native_readiness(
        driver.last_snapshot,
        probe=_Probe(),
        timeout_seconds=1,
        poll_seconds=1,
    )
    assert ready is False
    assert readiness_diagnostics == ["guest readiness requires concern-specific guest observation"]


def test_native_driver_rejects_inactive_daemon_readback_and_rolls_back(tmp_path):
    connection = _InactiveDomainConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )
    network, domain = _bounded_specs()

    result = driver.realize(networks=(network,), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault.observation-mismatch"]
    assert connection.domains[provider_resource_name(domain.address, prefix="native-test")].undefined is True
    assert connection.networks[provider_resource_name(network.address, prefix="native-test")].undefined is True
    assert driver.last_snapshot == {}


def test_native_driver_rejects_substituted_boot_artifact_readback(tmp_path):
    connection = _SubstitutedInitrdConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )
    network, domain = _bounded_specs()

    result = driver.realize(networks=(network,), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault.observation-mismatch"]
    assert connection.domains[provider_resource_name(domain.address, prefix="native-test")].undefined is True
    assert connection.networks[provider_resource_name(network.address, prefix="native-test")].undefined is True


def test_native_driver_rejects_extra_unbound_network_attachment(tmp_path):
    connection = _ExtraAttachmentConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )
    network, domain = _bounded_specs()

    result = driver.realize(networks=(network,), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault.observation-mismatch"]


def test_native_driver_rejects_substituted_network_forwarding_policy(tmp_path):
    connection = _WrongForwardModeConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )
    network, domain = _bounded_specs()
    network = replace(network, labels={"internal": "false"})

    result = driver.realize(networks=(network,), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault.observation-mismatch"]


def test_native_driver_rolls_back_when_evidence_binding_cannot_be_built(tmp_path, monkeypatch):
    connection = _FakeConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )
    network, domain = _bounded_specs()

    def _fail_binding(*_args):
        raise OSError("material unavailable")

    monkeypatch.setattr(driver, "_material_binding", _fail_binding)

    result = driver.realize(networks=(network,), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "libvirt-backend.techvault-native.operation-failed"
    ]
    assert connection.domains[provider_resource_name(domain.address, prefix="native-test")].undefined is True
    assert connection.networks[provider_resource_name(network.address, prefix="native-test")].undefined is True
    assert driver.last_snapshot == {}


def test_native_driver_does_not_claim_cleanup_when_native_listing_fails(tmp_path):
    connection = _UnverifiableDomainCleanupConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )
    network, domain = _bounded_specs()
    realized = driver.realize(networks=(network,), domains=(domain,))
    assert not realized.diagnostics

    result = driver.destroy(networks=(), domains=(domain.address,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == ["libvirt-backend.techvault-native.residual-state"]
    assert result.domains[0].realized is True


def test_native_driver_recovers_owned_resources_by_uuid_after_restart(tmp_path):
    connection = _FakeConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    network = NetworkSpec(
        address="provision.network.identity",
        name="lab-display",
        cidr="192.0.2.0/24",
        gateway="192.0.2.1",
        labels={"internal": "true"},
    )
    domain = DomainSpec(
        address="provision.node.identity",
        name="demo-display",
        image_ref=None,
        memory_mib=128,
        vcpus=1,
        networks=(network.address,),
    )
    first = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )
    assert not first.realize(networks=(network,), domains=(domain,)).diagnostics
    artifact_paths = tuple(path for paths in first._artifacts.values() for path in paths)
    assert all(path.exists() for path in artifact_paths)
    restarted = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        name_prefix="native-test",
        initramfs_builder=_Builder(),
    )

    result = restarted.destroy(networks=(network.address,), domains=(domain.address,))

    assert not result.diagnostics
    assert connection.domains[provider_resource_name(domain.address, prefix="native-test")].undefined is True
    assert connection.networks[provider_resource_name(network.address, prefix="native-test")].undefined is True
    assert all(not path.exists() for path in artifact_paths)


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        ({"memory_mib": 256}, "libvirt-backend.techvault.resource-out-of-envelope"),
        ({"image_ref": "requested.qcow2"}, "libvirt-backend.techvault.image-unsupported"),
        (
            {"services": (ServiceSpec(name="api", port=8443),)},
            "libvirt-backend.techvault.service-unsupported",
        ),
        (
            {"cloud_init": CloudInitSpec(users=(CloudInitUser(name="operator"),))},
            "libvirt-backend.techvault.guest-placement-unsupported",
        ),
        (
            {"cloud_init": CloudInitSpec(hostname="substituted")},
            "libvirt-backend.techvault.guest-placement-unsupported",
        ),
        ({"labels": {"unbound": "value"}}, "libvirt-backend.techvault.metadata-unsupported"),
        (
            {"network_acls": (NetworkAcl(name="deny", action="drop", direction="in", protocol="all"),)},
            "libvirt-backend.techvault.acl-unsupported",
        ),
    ),
)
def test_native_driver_direct_entrypoint_rejects_unsupported_domain_concerns(tmp_path, mutation, code):
    connection = _FakeConnection()
    driver = TechVaultNativeLibvirtDriver(state_dir=tmp_path / "state", connection=connection)
    domain = replace(
        DomainSpec(
            address="provision.node.demo",
            name="demo",
            image_ref=None,
            memory_mib=128,
            vcpus=1,
        ),
        **mutation,
    )

    result = driver.realize(networks=(), domains=(domain,))

    assert code in {diagnostic.code for diagnostic in result.diagnostics}
    assert connection.domain_xml == []
    assert connection.network_xml == []
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize(
    "network",
    (
        NetworkSpec(address="provision.network.lab", name="lab"),
        NetworkSpec(
            address="provision.network.lab",
            name="lab",
            cidr="192.0.2.0/24",
            gateway="192.0.2.1",
            labels={"internal": "implicit"},
        ),
        NetworkSpec(
            address="provision.network.lab",
            name="lab",
            cidr="192.0.2.0/24",
            gateway="192.0.2.1",
            labels={"internal": "true", "unbound": "value"},
        ),
    ),
)
def test_native_driver_direct_entrypoint_rejects_implicit_network_values(tmp_path, network):
    connection = _FakeConnection()
    driver = TechVaultNativeLibvirtDriver(state_dir=tmp_path / "state", connection=connection)

    result = driver.realize(networks=(network,), domains=())

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "libvirt-backend.techvault.network-exactness-required"
    ]
    assert connection.network_xml == []
    assert not (tmp_path / "state").exists()


def test_native_driver_rejects_network_without_deterministic_host_capacity(tmp_path):
    connection = _FakeConnection()
    driver = TechVaultNativeLibvirtDriver(state_dir=tmp_path / "state", connection=connection)
    network = NetworkSpec(
        address="provision.network.small",
        name="small",
        cidr="192.0.2.0/29",
        gateway="192.0.2.1",
        labels={"internal": "true"},
    )
    domain = DomainSpec(
        address="provision.node.demo",
        name="demo",
        image_ref=None,
        memory_mib=128,
        vcpus=1,
        networks=(network.address,),
    )

    result = driver.realize(networks=(network,), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "libvirt-backend.techvault.network-exactness-required"
    ]
    assert connection.network_xml == []
    assert connection.domain_xml == []
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("rollback_fails", (False, True))
def test_native_driver_verifies_partial_create_rollback_and_reports_residual_state(tmp_path, rollback_fails):
    connection = _SecondDomainFailsConnection(rollback_fails=rollback_fails)
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        initramfs_builder=_Builder(),
    )
    driver.last_snapshot = {"prior": "observation"}
    domains = tuple(
        DomainSpec(
            address=f"provision.node.demo-{index}",
            name=f"demo-{index}",
            image_ref=None,
            memory_mib=128,
            vcpus=1,
        )
        for index in (1, 2)
    )

    result = driver.realize(networks=(), domains=domains)

    assert result.domains == ()
    assert "libvirt-backend.techvault-native.operation-failed" in {diagnostic.code for diagnostic in result.diagnostics}
    first = connection.domains[provider_resource_name(domains[0].address, prefix="raes-techvault")]
    if rollback_fails:
        assert "libvirt-backend.techvault-native.residual-state" in {
            diagnostic.code for diagnostic in result.diagnostics
        }
        assert first.undefined is False
        assert list((tmp_path / "state" / "initramfs").glob("*.cpio.gz"))
    else:
        assert "libvirt-backend.techvault-native.residual-state" not in {
            diagnostic.code for diagnostic in result.diagnostics
        }
        assert first.destroyed is True
        assert first.undefined is True
        assert list((tmp_path / "state" / "initramfs").glob("*.cpio.gz")) == []
    assert driver.last_snapshot == {"prior": "observation"}


def test_native_driver_refuses_to_destroy_foreign_name_collision(tmp_path):
    connection = _FakeConnection()
    foreign_name = provider_resource_name("provision.node.demo", prefix="raes-techvault")
    foreign = _NativeObject(
        foreign_name,
        f"<domain><name>{foreign_name}</name><uuid>00000000-0000-4000-8000-000000000000</uuid></domain>",
    )
    foreign.created = True
    connection.domains[foreign.name()] = foreign
    driver = TechVaultNativeLibvirtDriver(state_dir=tmp_path / "state", connection=connection)

    result = driver.destroy(networks=(), domains=("provision.node.demo",))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "libvirt-backend.techvault-native.ownership-conflict"
    ]
    assert result.domains[0].realized is True
    assert foreign.destroyed is False
    assert foreign.undefined is False


def test_native_driver_refuses_to_replace_foreign_name_collision(tmp_path):
    connection = _FakeConnection()
    foreign_name = provider_resource_name("provision.node.demo", prefix="raes-techvault")
    foreign = _NativeObject(
        foreign_name,
        f"<domain><name>{foreign_name}</name><uuid>00000000-0000-4000-8000-000000000000</uuid></domain>",
    )
    foreign.created = True
    connection.domains[foreign.name()] = foreign
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        initramfs_builder=_Builder(),
    )
    domain = DomainSpec(
        address="provision.node.demo",
        name="demo",
        image_ref=None,
        memory_mib=128,
        vcpus=1,
    )

    result = driver.realize(networks=(), domains=(domain,))

    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "libvirt-backend.techvault-native.ownership-conflict"
    ]
    assert connection.domains[foreign.name()] is foreign
    assert foreign.destroyed is False
    assert foreign.undefined is False
    assert connection.domain_xml == []


def test_native_driver_destroy_is_idempotent_only_for_verified_absence(tmp_path):
    absent_driver = TechVaultNativeLibvirtDriver(state_dir=tmp_path / "absent", connection=_FakeConnection())

    absent = absent_driver.destroy(networks=(), domains=("provision.node.demo",))

    assert not absent.diagnostics
    assert absent.domains[0].realized is False

    uncertain_driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "uncertain",
        connection=_FailingLookupConnection(),
    )

    uncertain = uncertain_driver.destroy(networks=(), domains=("provision.node.demo",))

    assert [diagnostic.code for diagnostic in uncertain.diagnostics] == [
        "libvirt-backend.techvault-native.residual-state"
    ]
    assert uncertain.domains[0].realized is True


def test_validate_techvault_live_records_truthful_failed_manifest(tmp_path):
    scenario = EXAMPLES_DIR / "techvault-attacker-target.sdl.yaml"

    def _driver_factory():
        kernel = tmp_path / "vmlinuz-live"
        kernel.write_bytes(b"kernel")
        return TechVaultNativeLibvirtDriver(
            state_dir=tmp_path / "state",
            connection=_FakeConnection(),
            kernel_path=kernel,
            name_prefix="live-test",
            initramfs_builder=_Builder(),
        )

    report = validate_techvault_live(
        scenario_path=scenario,
        project_dir=tmp_path,
        run_id="native-live",
        config=TechVaultLiveConfig(),
        driver_factory=_driver_factory,
    )

    assert report.passed is False
    manifest = tmp_path / "runs" / "native-live" / "live-gate" / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["schema"] == "raes.libvirt.techvault-native-live-gate/v1"
    assert payload["scenario"]["path"] == "examples/scenarios/techvault-attacker-target.sdl.yaml"
    facts = payload["realization_facts"]
    assert facts["authored"]["source"] == "authored"
    assert facts["planned"]["source"] == "planned"
    assert facts["driver_reported"]["status"] == "failed"
    assert facts["daemon_observed"] == {"source": "daemon-observed", "domains": [], "networks": []}
    assert facts["guest_observed"] == {"source": "guest-observed", "status": "not-observed"}
    assert payload["validation"]["ok"] is False
    rendered = json.dumps(payload, sort_keys=True)
    assert "native-realized" not in rendered
    assert "soc_readback" not in rendered
    assert str(tmp_path) not in rendered


def test_validate_techvault_live_accepts_bounded_daemon_observed_substrate(tmp_path):
    connection = _FakeConnection()

    def _driver_factory():
        kernel = tmp_path / "vmlinuz-live"
        kernel.write_bytes(b"kernel")
        return TechVaultNativeLibvirtDriver(
            state_dir=tmp_path / "state",
            connection=connection,
            kernel_path=kernel,
            name_prefix="live-test",
            initramfs_builder=_Builder(),
        )

    report = validate_techvault_live(
        scenario_path=_bounded_scenario(tmp_path),
        project_dir=tmp_path,
        run_id="bounded-live",
        config=TechVaultLiveConfig(),
        driver_factory=_driver_factory,
    )

    assert report.passed, report.render()
    payload = json.loads(
        (tmp_path / "runs" / "bounded-live" / "live-gate" / "manifest.json").read_text(encoding="utf-8")
    )
    assert payload["realization_facts"]["daemon_observed"]["domains"] == [
        provider_resource_name("provision.node.demo", prefix="live-test")
    ]
    assert payload["realization_facts"]["guest_observed"]["status"] == "not-observed"
    assert payload["cleanup"] == {"source": "driver-reported", "status": "verified"}
    assert all(native.undefined for native in (*connection.domains.values(), *connection.networks.values()))
    assert "native-realized" not in json.dumps(payload, sort_keys=True)

    payload["realization_facts"]["planned"]["source"] = "daemon-observed"
    assert any("planned.source" in violation for violation in validate_techvault_live_manifest(payload))


def test_live_gate_has_no_aptl_or_docker_probe_dependency():
    source = Path(techvault_live.__file__).read_text(encoding="utf-8")
    assert "TechVaultComposeDriver" not in source
    assert "docker" not in source.lower()
    assert "aptl" not in source.lower()


def test_native_driver_refuses_prefix_wide_cleanup(tmp_path):
    connection = _FakeConnection()
    old_domain = _NativeObject("native-test-old-domain")
    old_network = _NativeObject("native-test-old-network")
    connection.domains[old_domain.name()] = old_domain
    connection.networks[old_network.name()] = old_network
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    with pytest.raises(ValueError, match="prefix-wide cleanup"):
        TechVaultNativeLibvirtDriver(
            state_dir=tmp_path / "state",
            connection=connection,
            kernel_path=kernel,
            name_prefix="native-test",
            initramfs_builder=_Builder(),
            clean_existing=True,
        )

    assert old_domain.destroyed is False
    assert old_network.destroyed is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"connection_uri": ""}, "non-empty"),
        ({"name_prefix": ""}, "non-empty"),
        ({"define_only": True}, "define-only"),
        ({"connection_uri": "qemu+ssh://operator:credential@example/system"}, "credentials"),
        ({"connection_uri": "qemu+ssh://operator@example/system"}, "credentials"),
        ({"name_prefix": "unsafe prefix"}, "libvirt-safe"),
    ),
)
def test_native_driver_rejects_unbound_material_or_secret_configuration(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        TechVaultNativeLibvirtDriver(state_dir=tmp_path / "state", **kwargs)


def test_native_driver_derives_provider_name_from_address_not_display_name(tmp_path):
    connection = _FakeConnection()
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")
    driver = TechVaultNativeLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        kernel_path=kernel,
        initramfs_builder=_Builder(),
    )
    domain = DomainSpec(
        address="provision.node.demo",
        name="unsafe name",
        image_ref=None,
        memory_mib=128,
        vcpus=1,
    )

    result = driver.realize(networks=(), domains=(domain,))

    assert not result.diagnostics
    assert provider_resource_name(domain.address, prefix="raes-techvault") in connection.domain_xml[0]
    assert "unsafe name" not in connection.domain_xml[0]


def test_init_script_accepts_a_decimal_string_cidr_prefix():
    script = _init_script(domain_with_interface(**{**VALID_INTERFACE, "cidr_prefix": "24"}))

    assert QUOTED_ADDRESS_COMMAND in script


def test_init_script_quotes_valid_interface_addressing():
    script = _init_script(domain_with_interface(**VALID_INTERFACE))

    assert QUOTED_MAC_ARM in script
    assert QUOTED_ADDRESS_COMMAND in script


@pytest.mark.parametrize(("interface", "match"), HOSTILE_INTERFACE_CASES)
def test_init_script_rejects_hostile_interface_fields_before_scripting(interface, match):
    domain = domain_with_interface(**interface)

    with pytest.raises(ValueError, match=match):
        _init_script(domain)


def test_init_script_skips_a_malformed_interface_entry_and_renders_the_rest():
    script = _init_script(domain_with_malformed_entry())

    assert "not-a-mapping" not in script
    assert QUOTED_MAC_ARM in script

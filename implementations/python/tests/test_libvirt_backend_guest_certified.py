"""Hermetic guest-certified libvirt driver + guest-observation coverage.

These tests exercise the guest-observation orchestration and its falsification
paths with a fake libvirt connection and a stub fact transport. They validate
staging, freshness, and concern comparison; per the preflight they cannot and do
not satisfy the native-proof gate (that is the opt-in real-daemon certification).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from libvirt_native_shapes import install_libvirt_error_type, libvirt_readback, lookup
from raes_backend_libvirt.cloudinit import CloudInitFile, CloudInitSpec, CloudInitUser
from raes_backend_libvirt.driver import DomainSpec, NetworkSpec, ServiceSpec
from raes_backend_libvirt.guest_appliance import _init_script, _write_placement_specs
from raes_backend_libvirt.guest_certified_driver import GuestCertifiedLibvirtDriver
from raes_backend_libvirt.guest_observation import (
    GuestObservationConfig,
    expected_guest_observations,
    guest_observation,
    guest_observation_diagnostics,
)
from raes_backend_libvirt.guest_transport import parse_guest_facts
from raes_backend_libvirt.techvault_matrix import domain_placements, mac_address
from raes_contracts.realization_envelope import RealizationConcern

_CHALLENGE = "deadbeefcafef00d"


@pytest.fixture(autouse=True)
def _libvirt_error_type(monkeypatch: pytest.MonkeyPatch) -> None:
    install_libvirt_error_type(monkeypatch)


@dataclass
class _StubTransport:
    facts_by_address: dict[str, str | None]
    failure: str | None = None

    def read(self, *, address, fact_channel_path, deadline_seconds):  # noqa: ANN001, ANN201
        del fact_channel_path, deadline_seconds
        if self.failure is not None:
            return None, self.failure
        return self.facts_by_address.get(address), None


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
        return libvirt_readback(self._xml)

    def UUIDString(self):  # noqa: N802 - mirrors libvirt API
        import xml.etree.ElementTree as ET

        return ET.fromstring(self._xml).findtext("uuid")  # noqa: S314 - test XML

    def destroy(self):
        self.destroyed = True

    def undefine(self):
        self.undefined = True


class _FakeConnection:
    def __init__(self) -> None:
        self.networks: dict[str, _NativeObject] = {}
        self.domains: dict[str, _NativeObject] = {}

    def networkDefineXML(self, xml: str):  # noqa: N802
        native = _NativeObject(_name_from_xml(xml), xml)
        self.networks[native.name()] = native
        return native

    def defineXML(self, xml: str):  # noqa: N802
        native = _NativeObject(_name_from_xml(xml), xml)
        self.domains[native.name()] = native
        return native

    def networkLookupByName(self, name: str):  # noqa: N802
        return lookup(self.networks, name, "networkLookupByName")

    def lookupByName(self, name: str):  # noqa: N802
        return lookup(self.domains, name, "lookupByName")

    def listAllDomains(self):  # noqa: N802
        return [native for native in self.domains.values() if not native.undefined]

    def listAllNetworks(self):  # noqa: N802
        return [native for native in self.networks.values() if not native.undefined]


def _name_from_xml(xml: str) -> str:
    start = xml.index("<name>") + len("<name>")
    return xml[start : xml.index("</name>")]


@dataclass
class _GuestFacts:
    challenge: str = _CHALLENGE
    architecture: str = "x86_64"
    vcpus: int = 1
    memory_mib: int = 120
    interfaces: list[tuple[str, str, int]] = field(default_factory=list)
    content: list[tuple[str, str, str]] = field(default_factory=list)
    accounts: list[tuple[str, int, str, str, int, str]] = field(default_factory=list)
    services: list[tuple[str, str, int, int, int]] = field(default_factory=list)
    init_complete: bool = True

    def render(self) -> str:
        lines = [
            "RAES-GUEST-FACTS v1",
            f"challenge {self.challenge}",
            f"architecture {self.architecture}",
            f"vcpus {self.vcpus}",
            f"memory_mib {self.memory_mib}",
        ]
        lines.extend(f"iface {mac} {ip} {up}" for mac, ip, up in self.interfaces)
        lines.extend(f"content {path} {digest} {mode}" for path, digest, mode in self.content)
        lines.extend(
            f"account {name} {uid} {home} {shell} {dis} {groups}"
            for name, uid, home, shell, dis, groups in self.accounts
        )
        lines.extend(
            f"service {name} {protocol} {port} {lis} {pid}" for name, protocol, port, lis, pid in self.services
        )
        if self.init_complete:
            lines.append("init complete")
        return "\n".join(lines) + "\n"


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _network() -> NetworkSpec:
    return NetworkSpec(
        address="scn.net",
        name="net",
        cidr="10.9.0.0/24",
        gateway="10.9.0.1",
        labels={"internal": "true"},
    )


def _domain() -> DomainSpec:
    return DomainSpec(
        address="scn.vm",
        name="vm",
        image_ref=None,
        memory_mib=128,
        vcpus=1,
        networks=("scn.net",),
        services=(ServiceSpec(name="beacon", port=9000),),
        cloud_init=CloudInitSpec(
            users=(
                CloudInitUser(  # noqa: S604 - `shell` is a CloudInitUser account field, not a subprocess shell
                    name="analyst", groups=("raes",), shell="/bin/sh", home="/home/analyst", lock_passwd=True
                ),
            ),
            write_files=(CloudInitFile(path="/etc/raes/marker", content="hello", permissions="0644"),),
        ),
    )


def _matching_facts() -> _GuestFacts:
    mac = mac_address("scn.vm", "scn.net")
    return _GuestFacts(
        interfaces=[(mac, "10.9.0.10", 1)],
        content=[("/etc/raes/marker", _sha("hello"), "644")],
        accounts=[("analyst", 1000, "/home/analyst", "/bin/sh", 1, "raes")],
        services=[("beacon", "tcp", 9000, 1, 1)],
    )


def _driver(
    tmp_path: Path,
    connection: _FakeConnection,
    transport: _StubTransport,
    *,
    challenge_factory=None,
    guest_config: GuestObservationConfig | None = None,
) -> GuestCertifiedLibvirtDriver:
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel-bytes")
    return GuestCertifiedLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=connection,
        name_prefix="raes-gc",
        kernel_path=kernel,
        initramfs_builder=_FakeBuilder(),
        guest_transport=transport,
        challenge_factory=challenge_factory or (lambda: _CHALLENGE),
        guest_config=guest_config or GuestObservationConfig(),
    )


def _realize(tmp_path: Path, facts: _GuestFacts | None, *, failure: str | None = None):
    connection = _FakeConnection()
    facts_map = {"scn.vm": facts.render() if facts is not None else None}
    transport = _StubTransport(facts_by_address=facts_map, failure=failure)
    driver = _driver(tmp_path, connection, transport)
    result = driver.realize(networks=(_network(),), domains=(_domain(),))
    return driver, connection, result


def _codes(result) -> set[str]:
    return {diag.code for diag in result.diagnostics}


def test_guest_certified_happy_path_realizes_and_certifies(tmp_path: Path) -> None:
    driver, connection, result = _realize(tmp_path, _matching_facts())
    assert result.diagnostics == ()
    assert {handle.address for handle in result.domains} == {"scn.vm"}
    guest_fields = {obs.field_path for obs in result.observations if obs.source.value == "guest-observed"}
    assert {
        "guest-architecture",
        "guest-vcpus",
        "guest-memory-mib",
        "guest-network",
        "guest-content",
        "guest-account",
        "guest-service",
    } <= guest_fields
    assert driver.last_guest_binding["challenge"] == _CHALLENGE
    assert driver.last_guest_binding["memory_tolerance_mib"] == 16
    assert "scn.vm" in driver.last_guest_facts
    memory = next(obs for obs in result.observations if obs.field_path == "guest-memory-mib")
    assert memory.value == 120
    service = next(obs for obs in result.observations if obs.field_path == "guest-service")
    assert service.value == ("beacon|tcp|9000|1|1",)
    # Native objects remain (committed), not rolled back.
    assert all(not native.destroyed for native in connection.domains.values())


def test_guest_service_protocol_is_bound_through_projection_artifact_and_facts(tmp_path: Path) -> None:
    placement = domain_placements(_domain())
    assert placement["services"] == [{"name": "beacon", "protocol": "tcp", "port": 9000}]

    guest_dir = tmp_path / "guest"
    files_dir = guest_dir / "files"
    files_dir.mkdir(parents=True)
    _write_placement_specs(guest_dir, files_dir, placement)
    assert (guest_dir / "services").read_text(encoding="utf-8") == "beacon|tcp|9000\n"

    script = _init_script({"name": "vm", "interfaces": [], **placement})
    assert "read name protocol port" in script
    assert "netstat -lnt" in script
    assert 'echo "service $name $protocol $port $lis $pid"' in script

    parsed = parse_guest_facts(_matching_facts().render())
    assert parsed is not None
    assert parsed["services"] == [
        {"name": "beacon", "protocol": "tcp", "port": 9000, "listening": True, "pid_present": True}
    ]


def test_guest_service_fact_without_protocol_is_not_accepted() -> None:
    text = _matching_facts().render().replace("service beacon tcp 9000 1 1", "service beacon 9000 1 1")
    parsed = parse_guest_facts(text)

    assert parsed is not None
    assert parsed["services"] == []


def test_udp_guest_service_is_rejected_before_native_mutation(tmp_path: Path) -> None:
    connection = _FakeConnection()
    driver = _driver(tmp_path, connection, _StubTransport(facts_by_address={}))
    domain = DomainSpec(
        address="scn.vm",
        name="vm",
        image_ref=None,
        memory_mib=128,
        vcpus=1,
        networks=("scn.net",),
        services=(ServiceSpec(name="beacon", protocol="udp", port=9000),),
    )

    result = driver.realize(networks=(_network(),), domains=(domain,))

    assert _codes(result) == {"libvirt-backend.techvault.service-unsupported"}
    assert connection.networks == {}
    assert connection.domains == {}


def test_default_challenge_factory_and_invalid_factory_are_explicit(tmp_path: Path) -> None:
    driver = GuestCertifiedLibvirtDriver(
        state_dir=tmp_path / "state",
        connection=_FakeConnection(),
        kernel_path=tmp_path / "kernel",
        initramfs_builder=_FakeBuilder(),
        guest_transport=_StubTransport(facts_by_address={}),
    )

    assert len(driver.challenge_factory()) == 32
    invalid_driver = {
        "state_dir": tmp_path / "bad-state",
        "connection": _FakeConnection(),
        "kernel_path": tmp_path / "kernel",
        "initramfs_builder": _FakeBuilder(),
        "guest_transport": _StubTransport(facts_by_address={}),
        "challenge_factory": None,
    }
    with pytest.raises(ValueError, match="must be callable"):
        GuestCertifiedLibvirtDriver(**invalid_driver)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("transport-unavailable", "libvirt-backend.guest.transport-unavailable"),
        ("boot-timeout", "libvirt-backend.guest.boot-timeout"),
    ],
)
def test_transport_stage_failures_are_typed_and_roll_back(tmp_path: Path, failure: str, expected_code: str) -> None:
    driver, connection, result = _realize(tmp_path, _matching_facts(), failure=failure)
    assert expected_code in _codes(result)
    assert driver.last_guest_observations == ()
    assert all(native.destroyed for native in connection.domains.values())


def test_missing_init_completion_fails(tmp_path: Path) -> None:
    facts = _matching_facts()
    facts.init_complete = False
    _, connection, result = _realize(tmp_path, facts)
    assert "libvirt-backend.guest.init-incomplete" in _codes(result)
    assert all(native.destroyed for native in connection.domains.values())


def test_stale_challenge_is_rejected(tmp_path: Path) -> None:
    facts = _matching_facts()
    facts.challenge = "0000000000000000"
    _, _, result = _realize(tmp_path, facts)
    assert "libvirt-backend.guest.challenge-mismatch" in _codes(result)


def test_prior_fact_channel_is_removed_before_native_mutation(tmp_path: Path) -> None:
    connection = _FakeConnection()
    transport = _StubTransport(facts_by_address={"scn.vm": _matching_facts().render()})
    driver = _driver(tmp_path, connection, transport)
    channel = driver._fact_channel_path("scn.vm")
    channel.parent.mkdir(parents=True)
    channel.write_text("stale completed report", encoding="utf-8")

    result = driver.realize(networks=(_network(),), domains=(_domain(),))

    assert result.diagnostics == ()
    assert not channel.exists()


def test_each_realize_operation_uses_a_new_challenge(tmp_path: Path) -> None:
    challenges = iter(("1111111111111111", "2222222222222222"))
    first_facts = _matching_facts()
    first_facts.challenge = "1111111111111111"
    transport = _StubTransport(facts_by_address={"scn.vm": first_facts.render()})
    driver = _driver(tmp_path, _FakeConnection(), transport, challenge_factory=challenges.__next__)

    first = driver.realize(networks=(_network(),), domains=(_domain(),))
    first_challenge = driver.challenge
    assert first.diagnostics == ()
    assert not driver.destroy(networks=("scn.net",), domains=("scn.vm",)).diagnostics
    driver.connection = _FakeConnection()
    second_facts = _matching_facts()
    second_facts.challenge = "2222222222222222"
    transport.facts_by_address["scn.vm"] = second_facts.render()
    second = driver.realize(networks=(_network(),), domains=(_domain(),))

    assert second.diagnostics == ()
    assert first_challenge == "1111111111111111"
    assert driver.challenge == "2222222222222222"


def test_reused_challenge_is_rejected_before_libvirt_mutation(tmp_path: Path) -> None:
    transport = _StubTransport(facts_by_address={"scn.vm": _matching_facts().render()})
    driver = _driver(tmp_path, _FakeConnection(), transport)
    assert not driver.realize(networks=(_network(),), domains=(_domain(),)).diagnostics
    assert not driver.destroy(networks=("scn.net",), domains=("scn.vm",)).diagnostics
    replacement = _FakeConnection()
    driver.connection = replacement

    second = driver.realize(networks=(_network(),), domains=(_domain(),))

    assert _codes(second) == {"libvirt-backend.guest.freshness-preflight-failed"}
    assert replacement.networks == {}
    assert replacement.domains == {}


def test_challenge_factory_failure_is_typed_before_libvirt_mutation(tmp_path: Path) -> None:
    def fail_challenge() -> str:
        raise RuntimeError("entropy unavailable")

    connection = _FakeConnection()
    driver = _driver(
        tmp_path,
        connection,
        _StubTransport(facts_by_address={}),
        challenge_factory=fail_challenge,
    )

    result = driver.realize(networks=(_network(),), domains=(_domain(),))

    assert _codes(result) == {"libvirt-backend.guest.freshness-preflight-failed"}
    assert connection.networks == {}
    assert connection.domains == {}


def test_fact_channel_directory_and_unlink_failure_fail_preflight(tmp_path: Path, monkeypatch) -> None:
    connection = _FakeConnection()
    driver = _driver(tmp_path, connection, _StubTransport(facts_by_address={}))
    channel = driver._fact_channel_path("scn.vm")
    channel.mkdir(parents=True)

    directory_result = driver.realize(networks=(_network(),), domains=(_domain(),))
    assert _codes(directory_result) == {"libvirt-backend.guest.freshness-preflight-failed"}
    assert connection.networks == {}
    channel.rmdir()
    channel.write_text("stale", encoding="utf-8")
    replacement = _FakeConnection()
    driver.connection = replacement
    driver.challenge_factory = lambda: "2222222222222222"
    original_unlink = Path.unlink

    def fail_channel_unlink(path: Path, *args, **kwargs):
        if path == channel:
            raise OSError("blocked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_channel_unlink)
    unlink_result = driver.realize(networks=(_network(),), domains=(_domain(),))

    assert _codes(unlink_result) == {"libvirt-backend.guest.freshness-preflight-failed"}
    assert replacement.networks == {}


def test_nonmapping_matrix_entry_is_ignored_during_fact_channel_preparation(tmp_path: Path) -> None:
    driver = _driver(tmp_path, _FakeConnection(), _StubTransport(facts_by_address={}))

    assert driver._prepare_operation({"domains": ["not-a-mapping"]}) == []
    assert driver.challenge == _CHALLENGE


def test_malformed_report_is_rejected(tmp_path: Path) -> None:
    connection = _FakeConnection()
    transport = _StubTransport(facts_by_address={"scn.vm": "not a fact report"})
    driver = _driver(tmp_path, connection, transport)
    result = driver.realize(networks=(_network(),), domains=(_domain(),))
    assert "libvirt-backend.guest.observation-malformed" in _codes(result)


@pytest.mark.parametrize(
    "mutate",
    ["ip", "vcpus", "memory", "content", "account", "service", "protocol", "missing_content"],
)
def test_concern_mismatches_are_falsified(tmp_path: Path, mutate: str) -> None:
    facts = _matching_facts()
    mac = mac_address("scn.vm", "scn.net")
    if mutate == "ip":
        facts.interfaces = [(mac, "10.9.0.99", 1)]
    elif mutate == "vcpus":
        facts.vcpus = 2
    elif mutate == "memory":
        facts.memory_mib = 8  # below the corroboration floor
    elif mutate == "content":
        facts.content = [("/etc/raes/marker", _sha("tampered"), "644")]
    elif mutate == "account":
        facts.accounts = [("analyst", 1000, "/home/analyst", "/bin/bash", 1, "raes")]
    elif mutate == "service":
        facts.services = [("beacon", "tcp", 9000, 0, 1)]
    elif mutate == "protocol":
        facts.services = [("beacon", "udp", 9000, 1, 1)]
    elif mutate == "missing_content":
        facts.content = []
    _, connection, result = _realize(tmp_path, facts)
    assert "libvirt-backend.guest.observation-mismatch" in _codes(result)
    assert all(native.destroyed for native in connection.domains.values())


@pytest.mark.parametrize(("observed", "passes"), ((112, True), (111, False), (64, False), (129, False)))
def test_memory_appraisal_uses_disclosed_one_sided_tolerance(tmp_path: Path, observed: int, passes: bool) -> None:
    facts = _matching_facts()
    facts.memory_mib = observed
    _, _, result = _realize(tmp_path, facts)

    assert (result.diagnostics == ()) is passes
    if not passes:
        assert "libvirt-backend.guest.observation-mismatch" in _codes(result)


def test_memory_tolerance_is_configurable_without_coarsening_evidence(tmp_path: Path) -> None:
    facts = _matching_facts()
    connection = _FakeConnection()
    transport = _StubTransport(facts_by_address={"scn.vm": facts.render()})
    driver = _driver(
        tmp_path,
        connection,
        transport,
        guest_config=GuestObservationConfig(memory_tolerance_mib=8),
    )

    result = driver.realize(networks=(_network(),), domains=(_domain(),))

    assert result.diagnostics == ()
    memory = next(obs for obs in result.observations if obs.field_path == "guest-memory-mib")
    assert memory.value == 120
    assert driver.last_guest_binding["memory_tolerance_mib"] == 8


@pytest.mark.parametrize("tolerance", (-1, True, "16"))
def test_invalid_memory_tolerance_is_rejected(tolerance) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        GuestObservationConfig(memory_tolerance_mib=tolerance)


def test_guest_observation_diagnostics_distinguish_missing_and_wrong_typed_facts() -> None:
    memory_key = ("scn.vm", "guest-memory-mib", RealizationConcern.RESOURCE_ALLOCATION)

    missing = guest_observation_diagnostics(expected={memory_key: 128}, observations=())
    wrong_type = guest_observation_diagnostics(
        expected={memory_key: 128},
        observations=(guest_observation("scn.vm", "guest-memory-mib", memory_key[2], "128"),),
    )

    assert [diagnostic.code for diagnostic in missing] == ["libvirt-backend.guest.observation-missing"]
    assert [diagnostic.code for diagnostic in wrong_type] == ["libvirt-backend.guest.observation-mismatch"]


def test_expected_guest_observations_ignore_nonmapping_accounts() -> None:
    expected = expected_guest_observations(
        [{"address": "scn.vm", "memory_mib": 128, "vcpus": 1, "accounts": ["not-a-mapping"]}]
    )

    key = ("scn.vm", "guest-account", RealizationConcern.ACCOUNT_PLACEMENT)
    assert expected[key] == ()


def test_failed_new_attempt_clears_prior_guest_evidence(tmp_path: Path) -> None:
    driver, _, first = _realize(tmp_path, _matching_facts())
    assert first.diagnostics == ()
    invalid = DomainSpec(
        address="scn.vm",
        name="vm",
        image_ref="unsupported.qcow2",
        memory_mib=128,
        vcpus=1,
        networks=("scn.net",),
    )

    second = driver.realize(networks=(_network(),), domains=(invalid,))

    assert "libvirt-backend.techvault.image-unsupported" in _codes(second)
    assert driver.challenge is None
    assert driver.last_guest_observations == ()
    assert driver.last_guest_facts == {}
    assert driver.last_guest_binding == {}


@pytest.mark.parametrize("second", ["vcpus 9", "vcpus 1", "challenge deadbeefcafef00d"])
def test_duplicate_singleton_fact_is_falsified(tmp_path: Path, second: str) -> None:
    # A repeated singleton fact (identical or conflicting) must be rejected distinctly
    # rather than silently collapsed to the last value.
    text = _matching_facts().render().replace("vcpus 1\n", f"vcpus 1\n{second}\n")
    connection = _FakeConnection()
    transport = _StubTransport(facts_by_address={"scn.vm": text})
    driver = _driver(tmp_path, connection, transport)
    result = driver.realize(networks=(_network(),), domains=(_domain(),))
    assert "libvirt-backend.guest.observation-duplicate" in _codes(result)
    assert all(native.destroyed for native in connection.domains.values())


def test_account_without_supplemental_groups_is_certified(tmp_path: Path) -> None:
    # An account with no supplemental groups is valid; the empty trailing groups
    # field must not cause the account observation to be dropped.
    mac = mac_address("scn.vm", "scn.net")
    domain = DomainSpec(
        address="scn.vm",
        name="vm",
        image_ref=None,
        memory_mib=128,
        vcpus=1,
        networks=("scn.net",),
        cloud_init=CloudInitSpec(
            # noqa below: `shell` is a CloudInitUser account field, not a subprocess shell.
            users=(CloudInitUser(name="loner", groups=(), shell="/bin/sh", home="/home/loner", lock_passwd=False),),  # noqa: S604
        ),
    )
    facts = _GuestFacts(
        interfaces=[(mac, "10.9.0.10", 1)],
        accounts=[("loner", 1000, "/home/loner", "/bin/sh", 0, "")],
    )
    connection = _FakeConnection()
    transport = _StubTransport(facts_by_address={"scn.vm": facts.render()})
    driver = _driver(tmp_path, connection, transport)
    result = driver.realize(networks=(_network(),), domains=(domain,))
    assert result.diagnostics == ()
    account_obs = next(obs for obs in result.observations if obs.field_path == "guest-account")
    assert account_obs.value == ("loner|/home/loner|/bin/sh|0|",)


def test_requested_image_is_rejected_before_mutation(tmp_path: Path) -> None:
    connection = _FakeConnection()
    transport = _StubTransport(facts_by_address={})
    driver = _driver(tmp_path, connection, transport)
    domain = DomainSpec(
        address="scn.vm", name="vm", image_ref="ubuntu:24.04", memory_mib=128, vcpus=1, networks=("scn.net",)
    )
    result = driver.realize(networks=(_network(),), domains=(domain,))
    assert "libvirt-backend.techvault.image-unsupported" in _codes(result)
    assert connection.domains == {}


def test_unsupported_placement_is_rejected(tmp_path: Path) -> None:
    connection = _FakeConnection()
    transport = _StubTransport(facts_by_address={})
    driver = _driver(tmp_path, connection, transport)
    domain = DomainSpec(
        address="scn.vm",
        name="vm",
        image_ref=None,
        memory_mib=128,
        vcpus=1,
        networks=("scn.net",),
        cloud_init=CloudInitSpec(packages=("nginx",)),
    )
    result = driver.realize(networks=(_network(),), domains=(domain,))
    assert "libvirt-backend.techvault.guest-placement-unsupported" in _codes(result)
    assert connection.domains == {}


# --- evidence-run integration (full control-plane pipeline) --------------------


class _FakeBuilder:
    def build(self, *, domain, target: Path):  # noqa: ANN001, ANN201
        del domain
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"initramfs")
        return target


def _bounded_guest_scenario(tmp_path: Path) -> Path:
    scenario = tmp_path / "guest-certified.sdl.yaml"
    scenario.write_text(
        """\
name: guest-certified
nodes:
  lab:
    type: switch
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
    return scenario


def _facts_from_matrix(matrix, challenge: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    for domain in matrix["domains"]:
        lines = [
            "RAES-GUEST-FACTS v1",
            f"challenge {challenge}",
            "architecture x86_64",
            f"vcpus {domain['vcpus']}",
            f"memory_mib {max(64, int(domain['memory_mib']) - 8)}",
        ]
        lines.extend(f"iface {iface['mac']} {iface['ip']} 1" for iface in domain["interfaces"])
        lines.append("init complete")
        facts[domain["address"]] = "\n".join(lines) + "\n"
    return facts


def _guest_matrix(scenario: Path):
    from raes.parser import parse_sdl_file
    from raes_backend_libvirt.manifest import create_libvirt_manifest
    from raes_backend_libvirt.realization import interpret_provisioning_plan
    from raes_backend_libvirt.techvault_matrix import native_matrix
    from raes_runtime.manager import RuntimeManager

    scout = GuestCertifiedLibvirtDriver(
        state_dir=scenario.parent / "scout",
        connection=_FakeConnection(),
        name_prefix="evidence-test",
        kernel_path=_write_kernel(scenario.parent),
        initramfs_builder=_FakeBuilder(),
        guest_transport=_StubTransport(facts_by_address={}),
        challenge_factory=lambda: _CHALLENGE,
    )
    from raes_backend_libvirt import create_libvirt_target

    target = create_libvirt_target(participant_runtime=True, driver=scout)
    plan = RuntimeManager(target).plan(parse_sdl_file(scenario)).provisioning
    capabilities = create_libvirt_manifest(driver_mode="guest-certified-appliance").capabilities.provisioner
    realization = interpret_provisioning_plan(plan, provisioner_capabilities=capabilities)
    return native_matrix(
        networks=realization.networks,
        domains=realization.domains,
        name_prefix="evidence-test",
        include_placements=True,
    )


def _write_kernel(directory: Path) -> Path:
    kernel = directory / "vmlinuz"
    kernel.write_bytes(b"kernel")
    return kernel


def _guest_factory(tmp_path: Path, transport: _StubTransport):
    def factory():
        return GuestCertifiedLibvirtDriver(
            state_dir=tmp_path / "state",
            connection=_FakeConnection(),
            name_prefix="evidence-test",
            kernel_path=_write_kernel(tmp_path),
            initramfs_builder=_FakeBuilder(),
            guest_transport=transport,
            challenge_factory=lambda: _CHALLENGE,
        )

    return factory


def test_evidence_run_guest_certified_publishes_bound_observations(tmp_path: Path) -> None:
    from raes_operations.libvirt_evidence_run import (
        LibvirtEvidenceRunConfig,
        run_libvirt_evidence_run,
        validate_libvirt_evidence_run_artifact,
    )

    scenario = _bounded_guest_scenario(tmp_path)
    facts = _facts_from_matrix(_guest_matrix(scenario), _CHALLENGE)
    transport = _StubTransport(facts_by_address=facts)
    report = run_libvirt_evidence_run(
        scenario_path=scenario,
        project_dir=tmp_path,
        run_id="gc-live-1",
        config=LibvirtEvidenceRunConfig(evidence_source_mode="guest-certified"),
        driver_factory=_guest_factory(tmp_path, transport),
    )
    assert report.passed, report.render()
    artifact = report.artifact
    assert artifact is not None
    assert validate_libvirt_evidence_run_artifact(artifact) == []
    guest = artifact["realization_facts"]["guest_observed"]
    assert guest["source"] == "guest-observed"
    assert guest["challenge"] == _CHALLENGE
    assert guest["memory_tolerance_mib"] == 16
    assert guest["operation_ref"].startswith("sha256:")
    # Native-proof boundary: an injected fake driver factory can exercise the
    # orchestration but must be marked non-certifying so its evidence can never be
    # published as a real guest certification.
    assert guest["certifying"] is False
    assert guest["domains"] and all(domain["correlation"].startswith("sha256:") for domain in guest["domains"])
    assert any(check.name == "native_substrate_cleanup" and check.passed for check in report.checks)


def test_evidence_run_guest_certified_transport_failure_fails_closed(tmp_path: Path) -> None:
    from raes_operations.libvirt_evidence_run import LibvirtEvidenceRunConfig, run_libvirt_evidence_run

    scenario = _bounded_guest_scenario(tmp_path)
    transport = _StubTransport(facts_by_address={}, failure="boot-timeout")
    report = run_libvirt_evidence_run(
        scenario_path=scenario,
        project_dir=tmp_path,
        run_id="gc-live-2",
        config=LibvirtEvidenceRunConfig(evidence_source_mode="guest-certified"),
        driver_factory=_guest_factory(tmp_path, transport),
    )
    assert not report.passed, report.render()
    assert report.artifact["backend"]["realization_provenance"]["substrate_realized"] is False
    assert report.artifact["realization_facts"]["guest_observed"] == {
        "source": "guest-observed",
        "status": "not-observed",
    }


def test_evidence_run_guest_certified_residual_probe_artifacts_fail_closed(tmp_path: Path) -> None:
    # Native domains/networks are torn down cleanly, but residual guest-probe state
    # survives: the run must fail closed rather than claim verified cleanup.
    from raes_operations.libvirt_evidence_run import LibvirtEvidenceRunConfig, run_libvirt_evidence_run

    class _ResidualGuestDriver(GuestCertifiedLibvirtDriver):
        def destroy(self, *, networks: tuple[str, ...], domains: tuple[str, ...]):
            result = super().destroy(networks=networks, domains=domains)
            self.last_guest_binding = {"challenge": self.challenge}
            return result

    scenario = _bounded_guest_scenario(tmp_path)
    facts = _facts_from_matrix(_guest_matrix(scenario), _CHALLENGE)
    transport = _StubTransport(facts_by_address=facts)

    def factory():
        return _ResidualGuestDriver(
            state_dir=tmp_path / "state",
            connection=_FakeConnection(),
            name_prefix="evidence-test",
            kernel_path=_write_kernel(tmp_path),
            initramfs_builder=_FakeBuilder(),
            guest_transport=transport,
            challenge_factory=lambda: _CHALLENGE,
        )

    report = run_libvirt_evidence_run(
        scenario_path=scenario,
        project_dir=tmp_path,
        run_id="gc-residual",
        config=LibvirtEvidenceRunConfig(evidence_source_mode="guest-certified"),
        driver_factory=factory,
    )
    assert not report.passed, report.render()
    cleanup = next(check for check in report.checks if check.name == "native_substrate_cleanup")
    assert not cleanup.passed
    assert any("guest probe artifacts were not fully cleaned" in diag for diag in cleanup.diagnostics)

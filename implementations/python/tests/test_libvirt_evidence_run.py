"""Coverage for the libvirt evidence-run evaluator-evidence artifact (issue #615).

Exercises the producer in both evidence-source modes against the reference scenario
(``enterprise-participant-evidence-loop.sdl.yaml``) and asserts every required evidence surface,
embedded-contract validity, the redaction gate, and the participant/evaluator
boundary. The native-live path is exercised with an injected fake libvirt
connection (no daemon), mirroring ``test_libvirt_backend_techvault_native``.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from libvirt_native_shapes import install_libvirt_error_type, libvirt_readback, lookup
from paths import EXAMPLES_DIR
from raes_backend_libvirt.techvault_native import TechVaultNativeLibvirtDriver
from raes_backend_protocols.naming import provider_resource_name
from raes_contracts.contracts import (
    BackendManifestV2Model,
    EvaluationHistoryEventModel,
    EvaluationResultStateModel,
    ExperimentRealizedFormDisclosureModel,
)
from raes_operations._evidence_run_realization import _validate_guest_metadata
from raes_operations.libvirt_evidence_run import (
    EVIDENCE_RUN_SCHEMA,
    LibvirtEvidenceRunConfig,
    run_libvirt_evidence_run,
    validate_libvirt_evidence_run_artifact,
)
from raes_operations.run_artifacts import (
    atomic_write_json_artifact,
    is_valid_run_id_label,
    run_artifact_path,
)

_REFERENCE_SCENARIO = EXAMPLES_DIR / "enterprise-participant-evidence-loop.sdl.yaml"
_TECHVAULT_SCENARIO = EXAMPLES_DIR / "techvault-operational.sdl.yaml"

_REQUIRED_SECTIONS = (
    "scenario",
    "compiled_artifact",
    "backend",
    "realization_facts",
    "realized_topology",
    "participant_action_proof",
    "terminal_observation",
    "defensive_evidence",
    "negative_boundary_checks",
    "evaluator_outcome",
    "realized_form_disclosures",
    "limitations",
    "non_claims",
    "redaction_provenance",
    "invariant_ledger_refs",
)


@pytest.mark.parametrize("invalid_tolerance", [True, -1, "16"])
def test_guest_evidence_requires_explicit_nonnegative_integer_memory_tolerance(invalid_tolerance: object) -> None:
    problems = _validate_guest_metadata(
        {
            "operation_ref": "sha256:" + "0" * 64,
            "certifying": True,
            "memory_tolerance_mib": invalid_tolerance,
            "observed_at": "2026-08-12T00:00:00Z",
            "probe_policy": "guest-probe/v1",
            "challenge": "fresh-challenge",
        }
    )

    assert problems == ["guest observation requires an explicit non-negative memory tolerance"]


# --- fake native libvirt substrate (no daemon) ---------------------------------


@pytest.fixture(autouse=True)
def _libvirt_error_type(monkeypatch: pytest.MonkeyPatch) -> None:
    install_libvirt_error_type(monkeypatch)


class _NativeObject:
    def __init__(self, name: str = "", xml: str = "") -> None:
        self._name = name
        self._xml = xml
        self._active = False
        self._undefined = False

    def name(self) -> str:
        return self._name

    def create(self) -> None:  # pragma: no cover - structural stub
        self._active = True

    def destroy(self) -> None:  # pragma: no cover - structural stub
        self._active = False

    def undefine(self) -> None:  # pragma: no cover - structural stub
        self._undefined = True

    def isActive(self):  # noqa: N802 - mirrors libvirt API
        return int(self._active)

    def XMLDesc(self, _flags=0):  # noqa: N802 - mirrors libvirt API
        return libvirt_readback(self._xml)

    def UUIDString(self):  # noqa: N802 - mirrors libvirt API
        return ET.fromstring(self._xml).findtext("uuid")  # noqa: S314 - test-generated XML


def _name_from_xml(xml: str) -> str:
    return xml[xml.index("<name>") + len("<name>") : xml.index("</name>")]


class _FakeConnection:
    def __init__(self) -> None:
        self.networks: dict[str, _NativeObject] = {}
        self.domains: dict[str, _NativeObject] = {}

    def networkDefineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        obj = _NativeObject(_name_from_xml(xml), xml)
        self.networks[obj.name()] = obj
        return obj

    def defineXML(self, xml: str):  # noqa: N802 - mirrors libvirt API
        obj = _NativeObject(_name_from_xml(xml), xml)
        self.domains[obj.name()] = obj
        return obj

    def networkLookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
        return lookup(self.networks, name, "networkLookupByName")

    def lookupByName(self, name: str):  # noqa: N802 - mirrors libvirt API
        return lookup(self.domains, name, "lookupByName")

    def listAllDomains(self):  # noqa: N802 - mirrors libvirt API
        return [item for item in self.domains.values() if not item._undefined]

    def listAllNetworks(self):  # noqa: N802 - mirrors libvirt API
        return [item for item in self.networks.values() if not item._undefined]


class _InitramfsBuilder:
    def build(self, *, domain, target: Path):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"initramfs")
        return target


def _native_driver_factory(tmp_path: Path):
    kernel = tmp_path / "vmlinuz"
    kernel.write_bytes(b"kernel")

    def factory() -> TechVaultNativeLibvirtDriver:
        return TechVaultNativeLibvirtDriver(
            state_dir=tmp_path / "state",
            connection=_FakeConnection(),
            kernel_path=kernel,
            name_prefix="evidence-test",
            initramfs_builder=_InitramfsBuilder(),
        )

    return factory


def _bounded_scenario(tmp_path: Path) -> Path:
    scenario = tmp_path / "bounded-techvault.sdl.yaml"
    scenario.write_text(
        """\
name: bounded-techvault
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


# --- deterministic mode --------------------------------------------------------


def test_deterministic_artifact_carries_all_evidence_surfaces(tmp_path):
    report = run_libvirt_evidence_run(scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-det-1")

    assert report.passed, report.render()
    artifact = report.artifact
    assert artifact is not None
    assert artifact["schema"] == EVIDENCE_RUN_SCHEMA
    assert artifact["evidence_source_mode"] == "deterministic"
    for section in _REQUIRED_SECTIONS:
        assert section in artifact, f"missing evidence surface: {section}"
    assert validate_libvirt_evidence_run_artifact(artifact) == []


def test_scenario_identity_is_portable_and_hashed(tmp_path):
    report = run_libvirt_evidence_run(scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-det-2")
    scenario = report.artifact["scenario"]
    assert scenario["name"] == "enterprise-participant-evidence-loop"
    assert scenario["content_sha256"].startswith("sha256:")
    # Portable ref, never the absolute host path.
    assert scenario["relative_path"] == "examples/scenarios/enterprise-participant-evidence-loop.sdl.yaml"
    assert not scenario["relative_path"].startswith("/")


def test_embedded_published_contracts_revalidate(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-det-3"
    ).artifact

    # The backend manifest is carried as the canonical BackendManifestV2 payload —
    # the same contract the rest of the stack uses — not a hand-rolled summary.
    manifest = artifact["backend"]["manifest"]
    BackendManifestV2Model.model_validate(manifest)
    assert manifest["identity"]["name"] == "libvirt-qemu"
    assert manifest["capabilities"]["participant_runtime"] is not None
    capability_profile = artifact["backend"]["capability_profile"]
    assert capability_profile["participant_runtime_contract_gaps"] == []
    assert capability_profile["observation_contract_gaps"] == []
    EvaluationResultStateModel.model_validate(artifact["evaluator_outcome"]["result"])
    for event in artifact["evaluator_outcome"]["history"]:
        EvaluationHistoryEventModel.model_validate(event)
    assert artifact["realized_form_disclosures"], "expected realized-form disclosures"
    for disclosure in artifact["realized_form_disclosures"]:
        ExperimentRealizedFormDisclosureModel.model_validate(disclosure)


def test_participant_action_proof_is_from_libvirt_runtime(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-det-4"
    ).artifact
    proof = artifact["participant_action_proof"]
    assert proof["lifecycle_clean"] is True
    assert proof["diagnostics"] == []
    assert proof["runtime"] == "libvirt-deterministic-participant-runtime"
    assert proof["admitted_action_addresses"], "expected at least one admitted action"
    # The participant surface exposes nothing of the internal/evaluator state.
    assert proof["participant_visible_refs"] == []
    assert proof["participant_disclosed_refs"] == []


def test_negative_boundary_withholds_internal_and_evaluator_surfaces(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-det-5"
    ).artifact
    boundary = artifact["negative_boundary_checks"]
    refs = {check["ref"] for check in boundary["checks"]}
    assert "nodes.customer-db.services.postgres" in refs
    assert "nodes.wazuh-manager" in refs
    assert "content.evaluator-notes" in refs
    assert boundary["all_internal_surfaces_withheld"] is True
    assert all(not check["exposed_to_participant"] for check in boundary["checks"])


def test_defensive_evidence_is_evaluator_only_with_disclosure(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-det-6"
    ).artifact
    defensive = artifact["defensive_evidence"]
    assert defensive["visibility"] == "evaluator-only"
    assert "loss_disclosure" in defensive
    assert "not upstream Wazuh" in defensive["loss_disclosure"]
    # Deterministic mode does not boot a live SOC stack.
    assert defensive["evidence_source"] == "structural-evaluator-channel"
    assert "soc_readback" not in defensive
    # captured_at is the shared run timestamp, not a freshly synthesized one.
    assert defensive["captured_at"] == artifact["recorded_at"]


def test_non_claims_are_carried_verbatim(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-det-7"
    ).artifact
    joined = " ".join(artifact["non_claims"])
    assert "No Wazuh detection-quality claim" in joined
    assert "No byte-equivalence" in joined
    assert "OpenRAE/rae#600" in joined


# --- redaction gate ------------------------------------------------------------


def test_artifact_contains_no_forbidden_secrets(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-redact-1"
    ).artifact
    blob = json.dumps(artifact)
    assert "/home/" not in blob
    assert "<domain" not in blob
    assert "qemu-system" not in blob
    assert "BEGIN PRIVATE KEY" not in blob
    assert "/var/lib/libvirt" not in blob


def test_validator_flags_injected_host_path_leak(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-redact-2"
    ).artifact
    artifact["realized_topology"]["leak"] = "/home/operator/.ssh/id_rsa"
    problems = validate_libvirt_evidence_run_artifact(artifact)
    assert any("redaction violation" in p for p in problems)


def test_validator_flags_injected_domain_uuid(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-redact-3"
    ).artifact
    artifact["realized_topology"]["leak_uuid"] = "550e8400-e29b-41d4-a716-446655440000"
    problems = validate_libvirt_evidence_run_artifact(artifact)
    assert any("domain UUID" in p for p in problems)


def test_validator_flags_participant_boundary_exposure(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-redact-4"
    ).artifact
    # Simulate a regression that leaks a withheld internal ref onto the participant view.
    artifact["participant_action_proof"]["participant_visible_refs"] = ["nodes.wazuh-manager"]
    problems = validate_libvirt_evidence_run_artifact(artifact)
    assert any("boundary violation" in p for p in problems)


def test_validator_rejects_nonempty_domain_list_as_daemon_observation(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO,
        project_dir=tmp_path,
        run_id="evidence-source-mutation-1",
    ).artifact
    envelope = artifact["backend"]["manifest"]["realization_envelope"]
    artifact["backend"]["realization_provenance"].update(
        {"substrate_realized": True, "basis": "daemon-observed-substrate"}
    )
    artifact["realized_topology"]["basis"] = "mixed-source"
    artifact["realization_facts"]["daemon_observed"]["domains"] = [
        {"name": "fabricated", "observation_source": "daemon-observed"}
    ]
    artifact["realization_facts"]["binding"] = {
        "driver": "techvault-appliance",
        "realization_envelope_digest": envelope["digest"],
        "configuration_digest": envelope["configuration_digest"],
        "driver_configuration_digest": "sha256:" + "0" * 64,
        "boot_artifact_digests": {},
    }

    problems = validate_libvirt_evidence_run_artifact(artifact)

    assert any("incomplete daemon domain observation" in problem for problem in problems)


def test_validator_rejects_planned_topology_relabelled_as_observed(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO,
        project_dir=tmp_path,
        run_id="evidence-source-mutation-2",
    ).artifact
    artifact["realized_topology"]["nodes"][0]["source"] = "daemon-observed"

    problems = validate_libvirt_evidence_run_artifact(artifact)

    assert any("realized_topology.nodes is planned" in problem for problem in problems)


def test_validator_rejects_native_realized_label_and_fabricated_soc_readback(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO,
        project_dir=tmp_path,
        run_id="evidence-source-mutation-3",
    ).artifact
    artifact["realized_topology"]["basis"] = "native-realized"
    artifact["defensive_evidence"]["soc_readback"] = {"wazuh_active_agents": ["fabricated"]}

    problems = validate_libvirt_evidence_run_artifact(artifact)

    assert any("native-realized" in problem for problem in problems)
    assert any("cannot supply SOC readback" in problem for problem in problems)


def test_validator_rejects_mismatched_realization_binding(tmp_path):
    artifact = run_libvirt_evidence_run(
        scenario_path=_bounded_scenario(tmp_path),
        project_dir=tmp_path,
        run_id="evidence-source-mutation-4",
        config=LibvirtEvidenceRunConfig(evidence_source_mode="native-live"),
        driver_factory=_native_driver_factory(tmp_path),
    ).artifact
    artifact["realization_facts"]["binding"]["realization_envelope_digest"] = "sha256:" + "f" * 64

    problems = validate_libvirt_evidence_run_artifact(artifact)

    assert any("envelope digest does not match" in problem for problem in problems)


# --- native-live mode ----------------------------------------------------------


def test_native_live_reference_scenario_discloses_unrealized_content_plane(tmp_path):
    report = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO,
        project_dir=tmp_path,
        run_id="evidence-live-1",
        config=LibvirtEvidenceRunConfig(evidence_source_mode="native-live"),
        driver_factory=_native_driver_factory(tmp_path),
    )
    # ASR-519: the TechVault appliance driver does not consume the generic cloud-init
    # content/account surfaces. A native domain must not hide that gap.
    assert report.passed is False
    artifact = report.artifact
    assert artifact is not None
    assert validate_libvirt_evidence_run_artifact(artifact) == []
    provenance = artifact["backend"]["realization_provenance"]
    assert provenance["substrate_realized"] is False
    unrealized = artifact["realized_topology"]["unrealized_capabilities"]
    assert unrealized, "orchestration/evaluation planes must still be disclosed, not faked"
    assert any("content" in cap.lower() or "account" in cap.lower() for cap in unrealized)


def test_native_live_realizes_substrate_for_provisionable_scenario(tmp_path):
    report = run_libvirt_evidence_run(
        scenario_path=_bounded_scenario(tmp_path),
        project_dir=tmp_path,
        run_id="tv-live-1",
        config=LibvirtEvidenceRunConfig(evidence_source_mode="native-live"),
        driver_factory=_native_driver_factory(tmp_path),
    )
    assert report.passed, report.render()
    artifact = report.artifact
    assert validate_libvirt_evidence_run_artifact(artifact) == []
    assert artifact["backend"]["realization_provenance"]["substrate_realized"] is True
    assert artifact["backend"]["realization_provenance"]["basis"] == "daemon-observed-substrate"
    assert artifact["backend"]["realization_provenance"]["cleanup_verified"] is True
    assert any(check.name == "native_substrate_cleanup" and check.passed for check in report.checks)
    assert artifact["realized_topology"]["basis"] == "mixed-source"
    native_surface = artifact["realized_topology"]["native_surface"]
    assert native_surface["source"] == "daemon-observed"
    assert native_surface["domains"] == (provider_resource_name("provision.node.demo", prefix="evidence-test"),)
    assert native_surface["networks"] == (provider_resource_name("provision.network.lab", prefix="evidence-test"),)
    facts = artifact["realization_facts"]
    assert facts["planned"]["source"] == "planned"
    assert facts["driver_reported"]["source"] == "driver-reported"
    assert facts["daemon_observed"]["source"] == "daemon-observed"
    assert facts["guest_observed"] == {"source": "guest-observed", "status": "not-observed"}
    assert (
        facts["binding"]["realization_envelope_digest"]
        == artifact["backend"]["manifest"]["realization_envelope"]["digest"]
    )
    defensive = artifact["defensive_evidence"]
    assert defensive["evidence_source"] == "structural-evaluator-channel"
    assert "soc_readback" not in defensive
    assert defensive["captured_at"] == artifact["recorded_at"]
    assert "native_reachability" not in artifact["negative_boundary_checks"]


def test_native_live_without_realized_substrate_fails(tmp_path):
    report = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO,
        project_dir=tmp_path,
        run_id="evidence-live-2",
        config=LibvirtEvidenceRunConfig(evidence_source_mode="native-live"),
    )
    # The default driver factory has no daemon to connect to, so nothing is realized.
    # The gating realization check fails: native-live cannot pass without realizing.
    # The artifact still builds and records substrate_realized=False.
    assert not report.passed, report.render()
    assert report.artifact["backend"]["realization_provenance"]["substrate_realized"] is False


# --- artifact write + run-id ---------------------------------------------------


def test_artifact_written_to_stable_path(tmp_path):
    report = run_libvirt_evidence_run(
        scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="evidence-write-1"
    )
    expected = tmp_path / "runs" / "evidence-write-1" / "scenario-evidence" / "libvirt-scenario-evidence-run.json"
    assert report.artifact_path == str(expected)
    assert expected.is_file()
    written = json.loads(expected.read_text())
    assert written["schema"] == EVIDENCE_RUN_SCHEMA


def test_unsafe_run_id_is_rejected_without_write(tmp_path):
    report = run_libvirt_evidence_run(scenario_path=_REFERENCE_SCENARIO, project_dir=tmp_path, run_id="../escape")
    assert not report.passed
    assert report.artifact_path is None
    assert not (tmp_path / "runs").exists()


# --- run_artifacts shared helper ----------------------------------------------


def test_run_id_label_validation():
    assert is_valid_run_id_label("evidence-run_2026.06.29")
    assert not is_valid_run_id_label("../escape")
    assert not is_valid_run_id_label(".hidden")
    assert not is_valid_run_id_label("with/slash")
    assert not is_valid_run_id_label("")


def test_run_artifact_path_rejects_unsafe_label(tmp_path):
    with pytest.raises(ValueError, match="safe filesystem label"):
        run_artifact_path(tmp_path, "../escape", "scenario-evidence", "run.json")


def test_atomic_write_json_artifact_round_trips(tmp_path):
    target = tmp_path / "runs" / "r1" / "sub" / "artifact.json"
    atomic_write_json_artifact(target, {"b": 2, "a": 1})
    text = target.read_text()
    # Canonical serialization: sorted keys, indent 2, trailing newline, no temp files left.
    assert text == '{\n  "a": 1,\n  "b": 2\n}\n'
    assert list(target.parent.glob("*.tmp")) == []

"""ASR-525 conformance corpus and independent-demand probes (#340, #1198)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes.observability_plane_semantics import (
    ObservabilityEvidencePlane,
    classify_contract_plane,
    classify_runtime_family,
    classify_sdl_section_plane,
    collect_scenario_native_observability_refs,
)
from raes.parser import parse_sdl
from raes_conformance.conformance import (
    observability_evidence_conformance_diagnostics,
    run_fixture_suite,
)
from raes_contracts.contracts import ExperimentRunModel
from raes_processor.compiler import compile_scenario_runtime_model

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_FIXTURE = (
    REPO_ROOT / "contracts" / "fixtures" / "experiment-core" / "experiment-run-v1" / "valid" / "reference.json"
)
FIXTURES_ROOT = REPO_ROOT / "contracts" / "fixtures"
SDL_FIXTURES = FIXTURES_ROOT / "sdl" / "sdl-yaml-v1" / "valid"


@pytest.fixture(scope="module")
def observability_report():
    return run_fixture_suite(profile="observability-evidence")


def test_published_observability_profile_exercises_plane_boundaries(observability_report) -> None:
    report = observability_report
    assert report.passed, report.diagnostics
    assert {case.contract_name for case in report.cases} == {
        "backend-manifest-v2",
        "experiment-capture-spec-v1",
        "experiment-evidence-record-v1",
        "experiment-derived-measure-v1",
        "experiment-run-v1",
    }
    assert report.native_conformance is False
    assert {case.execution_basis for case in report.cases} == {"fixture-only"}
    cases = {(case.contract_name, case.name): case for case in report.cases}
    for contract, name in (
        ("experiment-evidence-record-v1", "sem224-capture-record-without-requirement-ref"),
        ("experiment-evidence-record-v1", "sem216-analysis-output-as-evidence"),
        ("experiment-derived-measure-v1", "missing-source-evidence"),
    ):
        case = cases[contract, name]
        assert not case.valid
        assert case.passed
        assert {diagnostic.code for diagnostic in case.diagnostics} == {"conformance.schema-invalid"}
    assert classify_contract_plane("backend-manifest-v2") is ObservabilityEvidencePlane.PROCESSOR_BACKEND_OPERATIONAL
    assert (
        classify_contract_plane("experiment-capture-spec-v1")
        is ObservabilityEvidencePlane.AUTHORED_EVIDENCE_REQUIREMENT
    )
    assert classify_contract_plane("experiment-evidence-record-v1") is ObservabilityEvidencePlane.CAPTURED_EVIDENCE
    assert classify_contract_plane("experiment-derived-measure-v1") is ObservabilityEvidencePlane.DERIVED_ANALYSIS


@pytest.mark.parametrize(
    ("name", "valid", "code"),
    [
        ("augmentation-classifications", True, None),
        ("augmentation-without-affected-refs", False, "conformance.observability-evidence-invalid"),
        ("augmentation-without-portable-carrier", False, "conformance.observability-evidence-invalid"),
        ("augmentation-purpose-without-evidence", False, "conformance.observability-evidence-invalid"),
        ("augmentation-environment-without-effect", False, "conformance.schema-invalid"),
        ("augmentation-participant-without-markings", False, "conformance.schema-invalid"),
        ("augmentation-comparability-without-observer-effect", False, "conformance.schema-invalid"),
    ],
)
def test_published_augmentation_cases(observability_report, name: str, valid: bool, code: str | None) -> None:
    case = next(case for case in observability_report.cases if case.name == name)
    assert case.contract_name == "experiment-run-v1"
    assert case.valid is valid
    assert case.passed
    assert {diagnostic.code for diagnostic in case.diagnostics} == (set() if code is None else {code})


def test_augmentation_fixture_preserves_conditional_evidence() -> None:
    payload = json.loads((RUN_FIXTURE.parent / "augmentation-classifications.json").read_text(encoding="utf-8"))
    schema_path = REPO_ROOT / "contracts/schemas/experiment-core/experiment-run-v1.json"
    Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(payload)
    run = ExperimentRunModel.model_validate(payload)
    disclosures = {disclosure.augmentation_id: disclosure for disclosure in run.augmentation_disclosures}
    operational = disclosures["operational-apparatus"]
    assert operational.classifications == ["apparatus_only"]
    assert operational.purpose == "operational"
    assert operational.evidence_refs == []
    assert set(disclosures["combined-augmentation"].classifications) == {
        "apparatus_only",
        "environment_visible",
        "participant_visible",
        "comparability_relevant",
    }
    assert observability_evidence_conformance_diagnostics(run) == ()


def test_published_profile_detects_corrupted_valid_augmentation(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    # Copy only this profile's carriers, preserving valid and invalid controls.
    for contract, family in (
        ("backend-manifest-v2", "backend-manifest"),
        ("experiment-capture-spec-v1", "experiment-core"),
        ("experiment-evidence-record-v1", "experiment-core"),
        ("experiment-derived-measure-v1", "experiment-core"),
        ("experiment-run-v1", "experiment-core"),
    ):
        shutil.copytree(FIXTURES_ROOT / family / contract, root / family / contract)
    path = root / "experiment-core/experiment-run-v1/valid/augmentation-classifications.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["augmentation_disclosures"][0]["affected_refs"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = run_fixture_suite(profile="observability-evidence", root=root)

    assert not report.passed
    failed = [case for case in report.cases if not case.passed]
    assert len(failed) == 1
    assert failed[0].name == "augmentation-classifications"
    assert failed[0].valid
    assert {diagnostic.code for diagnostic in failed[0].diagnostics} == {"conformance.observability-evidence-invalid"}
    assert failed[0].diagnostics[0].address.endswith(".affected_refs")


@pytest.mark.parametrize("field", ["ref_id", "ref_version"])
def test_augmentation_evidence_requires_exact_run_traceability(field: str) -> None:
    payload = _reference_run()
    disclosure = _augmentation_disclosure()
    disclosure["evidence_refs"][0][field] = "not-run-traced"
    payload["augmentation_disclosures"] = [disclosure]
    with pytest.raises(ValidationError, match="augmentation_disclosures evidence_refs must be listed"):
        ExperimentRunModel.model_validate(payload)


def test_native_observability_does_not_create_experimental_demand() -> None:
    scenario = parse_sdl((SDL_FIXTURES / "observability-native-no-demand.yaml").read_text(encoding="utf-8"))
    assert "nodes.monitor.runtime.service_listeners.telemetry" in collect_scenario_native_observability_refs(scenario)
    assert classify_runtime_family("service_listeners") is ObservabilityEvidencePlane.SCENARIO_NATIVE_OBSERVABILITY
    assert scenario.evidence_requirements == {}
    assert compile_scenario_runtime_model(scenario).observation_demands == ()


def test_authored_capture_demand_is_separate_from_native_source() -> None:
    scenario = parse_sdl((SDL_FIXTURES / "observability-selected-demand.yaml").read_text(encoding="utf-8"))
    assert (
        classify_sdl_section_plane("evidence_requirements") is ObservabilityEvidencePlane.AUTHORED_EVIDENCE_REQUIREMENT
    )
    source = "nodes.monitor.runtime.service_listeners.telemetry"
    assert scenario.evidence_requirements["listener-events"].source_refs == [source]
    assert source in collect_scenario_native_observability_refs(scenario)
    demands = compile_scenario_runtime_model(scenario).observation_demands
    assert len(demands) == 1
    demand = demands[0]
    assert demand.scope == "/nodes/monitor"
    assert demand.purpose.value == "experimental"
    assert demand.collection.value == "require"
    assert demand.retention.value == "disable"
    assert demand.export.value == "disable"
    assert demand.selectors[0].names == ("listener-events",)


def _reference_run() -> dict:
    return json.loads(RUN_FIXTURE.read_text(encoding="utf-8"))


def _augmentation_disclosure() -> dict:
    return {
        "augmentation_id": "packet-capture-sidecar",
        "purpose": "evidence",
        "realization_layer": "backend",
        "classifications": ["apparatus_only", "comparability_relevant"],
        "augmented_by_ref": {
            "ref_kind": "backend",
            "ref_id": "stub-backend",
            "ref_version": "0.1.0",
        },
        "carrier_refs": [
            {
                "ref_kind": "measurement-channel",
                "ref_id": "evaluation-history-channel",
                "ref_version": "1.0.0",
            }
        ],
        "affected_refs": [
            {
                "ref_kind": "capture-spec",
                "ref_id": "capture-techvault-evidence-v1",
                "ref_version": "1.0.0",
            }
        ],
        "evidence_refs": [
            {
                "ref_kind": "evidence-record",
                "ref_id": "evidence-techvault-network-trace-001",
                "ref_version": "1.0.0",
            }
        ],
        "disclosure_policy": "Internal run-provenance disclosure; no raw packet content is embedded.",
        "markings": ["internal"],
        "observer_effect": "The sidecar observes run traffic without modifying scenario services.",
        "comparability_effect": "Compare only with runs that declare equivalent capture support.",
    }


def test_observability_evidence_conformance_accepts_traced_augmentation() -> None:
    payload = _reference_run()
    payload["augmentation_disclosures"] = [_augmentation_disclosure()]

    diagnostics = observability_evidence_conformance_diagnostics(payload)

    assert diagnostics == ()


def test_observability_evidence_conformance_requires_affected_refs() -> None:
    payload = _reference_run()
    disclosure = _augmentation_disclosure()
    disclosure["affected_refs"] = []
    payload["augmentation_disclosures"] = [disclosure]

    diagnostics = observability_evidence_conformance_diagnostics(payload)

    assert {diagnostic.code for diagnostic in diagnostics} == {"conformance.observability-evidence-invalid"}
    assert any("affected_refs" in diagnostic.address for diagnostic in diagnostics)
    assert any("must name affected_refs" in diagnostic.message for diagnostic in diagnostics)


def test_observability_evidence_conformance_requires_authored_ref_for_run_refinement() -> None:
    payload = _reference_run()
    payload["realized_form_disclosures"].append(
        {
            "concern_id": "capture-window-tightening",
            "concern_kind": "capture-window",
            "basis": "processor-realized",
            "realized_by_ref": {
                "ref_kind": "processor",
                "ref_id": "raes-reference-processor",
                "ref_version": "0.1.0",
            },
            "realized_value_summary": "Run used a narrower post-condition capture window.",
            "disclosure": "The processor narrowed the capture window for this run without rewriting the authored requirement.",
            "evidence_refs": [],
        }
    )

    diagnostics = observability_evidence_conformance_diagnostics(payload)

    assert {diagnostic.code for diagnostic in diagnostics} == {"conformance.observability-evidence-invalid"}
    assert any("authored_ref" in diagnostic.message for diagnostic in diagnostics)
    assert any("evidence_refs" in diagnostic.message for diagnostic in diagnostics)


def test_fixture_suite_exercises_experiment_run_observability_semantics(observability_report) -> None:
    report = observability_report

    assert report.passed is True
    invalid_case = next(case for case in report.cases if case.name == "augmentation-without-affected-refs")
    assert invalid_case.valid is False
    assert invalid_case.passed is True
    assert any(
        diagnostic.code == "conformance.observability-evidence-invalid" for diagnostic in invalid_case.diagnostics
    )

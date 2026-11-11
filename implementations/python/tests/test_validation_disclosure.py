"""ASR-515 governed validation-basis disclosure tests."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from raes.canonical import (
    INSTANTIATED_SNAPSHOT_PROFILE,
    InstantiatedScenarioSnapshot,
    canonical_instantiated_sdl_digest,
    canonical_sdl_digest,
)
from raes.instantiate import instantiate_scenario
from raes.parser import parse_sdl
from raes_conformance.conformance import _fixture_case_diagnostics
from raes_contracts.contracts import ExperimentRunModel, ExperimentStudyModel, ExperimentTaskModel
from raes_contracts.contracts.validation_disclosure import (
    ValidationBasisDisclosureDocumentModel,
    ValidationBasisDisclosureModel,
    ValidationGateResultModel,
    ValidationSubjectReferenceModel,
)
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_ROOT = REPO_ROOT / "contracts/fixtures/profiles/validation-basis-disclosure-v1"

_SNAPSHOT_SDL = """\
name: validation-basis-snapshot
nodes:
  target:
    type: compute
    os: linux
"""
_SNAPSHOT_SDL_MUTATED = """\
name: validation-basis-snapshot
nodes:
  target:
    type: compute
    os: windows
"""


def _snapshot(sdl: str = _SNAPSHOT_SDL) -> InstantiatedScenarioSnapshot:
    scenario = parse_sdl(sdl)
    instantiated = instantiate_scenario(scenario, parameters={})
    return InstantiatedScenarioSnapshot(profile=INSTANTIATED_SNAPSHOT_PROFILE, scenario=instantiated)


def _gate(gate_kind: str, outcome: str = "passed", **overrides: Any) -> dict[str, Any]:
    payload = {"gate_kind": gate_kind, "outcome": outcome}
    payload.update(overrides)
    return payload


_STRUCTURAL_GATES = ["syntax_validation", "schema_validation", "vocabulary_validation"]
_SEMANTIC_REQUIRED_GATES = [
    *_STRUCTURAL_GATES,
    "semantic_invariant_validation",
    "reference_resolution",
    "lifecycle_separation",
    "cross_artifact_consistency",
]
_BEHAVIORAL_REQUIRED_GATES = [
    *_SEMANTIC_REQUIRED_GATES,
    "behavioral_execution",
    "governed_diagnostics",
]
_EVIDENCE_BACKED_REQUIRED_GATES = [
    *_STRUCTURAL_GATES,
    "semantic_invariant_validation",
    "reference_resolution",
    "evidence_preservation",
    "provenance_validation",
    "limitation_disclosure",
]
_FALSIFICATION_BACKED_REQUIRED_GATES = [
    *_EVIDENCE_BACKED_REQUIRED_GATES,
    "falsification_protocol",
    "evidence_status",
]


def _structural_disclosure_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile_id": "raes-structural-validation",
        "profile_version": "v1",
        "subject_kind": "scenario",
        "subject_ref": {"ref_kind": "scenario", "ref_id": "scenario-1"},
        "achieved_strength": "structural",
        "gate_results": [_gate(kind) for kind in _STRUCTURAL_GATES],
        "recorded_at": "2026-07-24T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _semantic_disclosure_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile_id": "raes-semantic-validation",
        "profile_version": "v1",
        "subject_kind": "scenario_snapshot",
        "subject_ref": {
            "ref_kind": "scenario-snapshot",
            "ref_id": "scenario-1",
            "ref_digest": "sha256:" + "a" * 64,
        },
        "achieved_strength": "semantic",
        "gate_results": [_gate(kind) for kind in _SEMANTIC_REQUIRED_GATES],
        "recorded_at": "2026-07-24T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _behavioral_disclosure_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile_id": "raes-behavioral-validation",
        "profile_version": "v1",
        "subject_kind": "experiment_task",
        "subject_ref": {"ref_kind": "task", "ref_id": "task-1", "ref_version": "v1"},
        "achieved_strength": "behavioral",
        "gate_results": [_gate(kind) for kind in _BEHAVIORAL_REQUIRED_GATES],
        "recorded_at": "2026-07-24T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _evidence_backed_disclosure_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile_id": "raes-evidence-backed-validation",
        "profile_version": "v1",
        "subject_kind": "experiment_run",
        "subject_ref": {"ref_kind": "run", "ref_id": "run-1", "ref_version": "v1"},
        "achieved_strength": "evidence_backed",
        "gate_results": [_gate(kind) for kind in _EVIDENCE_BACKED_REQUIRED_GATES],
        "evidence_refs": [{"ref_kind": "evidence-record", "ref_id": "evidence-1"}],
        "recorded_at": "2026-07-24T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _falsification_backed_disclosure_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile_id": "raes-falsification-backed-validation",
        "profile_version": "v1",
        "subject_kind": "published_claim",
        "subject_ref": {"ref_kind": "result", "ref_id": "claim-1"},
        "achieved_strength": "falsification_backed",
        "gate_results": [_gate(kind) for kind in _FALSIFICATION_BACKED_REQUIRED_GATES],
        "evidence_refs": [{"ref_kind": "evidence-record", "ref_id": "evidence-1"}],
        "recorded_at": "2026-07-24T00:00:00Z",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# Happy path per strength                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "builder",
    [
        _structural_disclosure_payload,
        _semantic_disclosure_payload,
        _behavioral_disclosure_payload,
        _evidence_backed_disclosure_payload,
        _falsification_backed_disclosure_payload,
    ],
)
def test_valid_disclosure_accepted_for_each_strength(builder: Any) -> None:
    disclosure = ValidationBasisDisclosureModel.model_validate(builder())
    assert disclosure.achieved_strength in {
        "structural",
        "semantic",
        "behavioral",
        "evidence_backed",
        "falsification_backed",
    }


def test_document_wrapper_requires_schema_version_and_embeds_core() -> None:
    document = ValidationBasisDisclosureDocumentModel.model_validate(
        {
            "schema_version": "validation-basis-disclosure/v1",
            "disclosure": _structural_disclosure_payload(),
        }
    )
    assert document.disclosure.profile_id == "raes-structural-validation"

    invalid_document = {"schema_version": "wrong/v1", "disclosure": _structural_disclosure_payload()}
    with pytest.raises(ValidationError):
        ValidationBasisDisclosureDocumentModel.model_validate(invalid_document)


# --------------------------------------------------------------------------- #
# Gate-result shape                                                           #
# --------------------------------------------------------------------------- #


def test_gate_result_not_applicable_requires_detail() -> None:
    with pytest.raises(ValidationError, match="not_applicable"):
        ValidationGateResultModel.model_validate({"gate_kind": "behavioral_execution", "outcome": "not_applicable"})

    gate = ValidationGateResultModel.model_validate(
        {"gate_kind": "behavioral_execution", "outcome": "not_applicable", "detail": "no runtime path executed"}
    )
    assert gate.outcome == "not_applicable"


# --------------------------------------------------------------------------- #
# Profile-join fail-closed behavior                                          #
# --------------------------------------------------------------------------- #


def test_disclosure_fails_closed_for_unknown_profile_identity() -> None:
    payload = _structural_disclosure_payload(profile_id="raes-missing-validation")
    with pytest.raises(ValidationError, match="unknown validation profile"):
        ValidationBasisDisclosureModel.model_validate(payload)


def test_disclosure_fails_closed_for_subject_kind_not_declared_by_profile() -> None:
    payload = _structural_disclosure_payload(
        profile_id="raes-behavioral-validation",
        subject_kind="published_claim",
        subject_ref={"ref_kind": "result", "ref_id": "claim-1"},
        gate_results=[_gate(kind) for kind in _BEHAVIORAL_REQUIRED_GATES],
        achieved_strength="behavioral",
    )
    with pytest.raises(ValidationError, match="does not declare subject kind"):
        ValidationBasisDisclosureModel.model_validate(payload)


# --------------------------------------------------------------------------- #
# subject_kind -> ref_kind mapping (ONE explicit mapping)                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("subject_kind", "ref_kind"),
    [
        ("scenario", "scenario"),
        ("scenario_snapshot", "scenario-snapshot"),
        ("experiment_task", "task"),
        ("experiment_run", "run"),
        ("experiment_study", "study"),
        ("backend_conformance_claim", "backend"),
        ("participant_conformance_claim", "participant-implementation"),
        ("published_claim", "result"),
    ],
)
def test_subject_kind_ref_kind_mapping_accepts_correct_pairing(subject_kind: str, ref_kind: str) -> None:
    subject_ref: dict[str, Any] = {"ref_kind": ref_kind, "ref_id": "subject-1"}
    if ref_kind == "scenario-snapshot":
        subject_ref["ref_digest"] = "sha256:" + "b" * 64
    if ref_kind in {"task", "run", "study"}:
        subject_ref["ref_version"] = "v1"
    payload = _structural_disclosure_payload(
        profile_id="raes-structural-validation",
        subject_kind=subject_kind,
        subject_ref=subject_ref,
    )
    disclosure = ValidationBasisDisclosureModel.model_validate(payload)
    assert disclosure.subject_ref.ref_kind == ref_kind


@pytest.mark.parametrize(
    ("subject_kind", "wrong_ref_kind"),
    [
        ("scenario", "task"),
        ("scenario_snapshot", "scenario"),
        ("experiment_task", "run"),
        ("experiment_run", "study"),
        ("experiment_study", "task"),
        ("backend_conformance_claim", "participant-implementation"),
        ("participant_conformance_claim", "backend"),
        ("published_claim", "task"),
    ],
)
def test_subject_kind_ref_kind_mapping_rejects_wrong_pairing(subject_kind: str, wrong_ref_kind: str) -> None:
    subject_ref: dict[str, Any] = {"ref_kind": wrong_ref_kind, "ref_id": "subject-1"}
    if wrong_ref_kind in {"task", "run", "study"}:
        subject_ref["ref_version"] = "v1"
    payload = _structural_disclosure_payload(
        subject_kind=subject_kind,
        subject_ref=subject_ref,
    )
    with pytest.raises(ValidationError, match="requires subject_ref.ref_kind"):
        ValidationBasisDisclosureModel.model_validate(payload)


def test_scenario_snapshot_subject_reference_requires_digest() -> None:
    payload = _structural_disclosure_payload(
        subject_kind="scenario_snapshot",
        subject_ref={"ref_kind": "scenario-snapshot", "ref_id": "scenario-1"},
    )
    with pytest.raises(ValidationError, match="ref_digest"):
        ValidationBasisDisclosureModel.model_validate(payload)


def test_generic_scenario_subject_reference_rejects_digest() -> None:
    payload = _structural_disclosure_payload(
        subject_ref={"ref_kind": "scenario", "ref_id": "scenario-1", "ref_digest": "sha256:" + "c" * 64}
    )
    with pytest.raises(ValidationError, match="must not carry ref_digest"):
        ValidationBasisDisclosureModel.model_validate(payload)


# --------------------------------------------------------------------------- #
# Versioned carrier subject kinds (task/run/study) must bind ref_version --   #
# omitting it would let a disclosure be replayed across revisions sharing an  #
# id (issue #259 CLASS finding).                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("ref_kind", ["task", "run", "study"])
def test_versioned_subject_reference_requires_ref_version(ref_kind: str) -> None:
    with pytest.raises(ValidationError, match="must include ref_version"):
        ValidationSubjectReferenceModel.model_validate({"ref_kind": ref_kind, "ref_id": "subject-1"})


@pytest.mark.parametrize(
    ("subject_kind", "ref_kind"),
    [
        ("experiment_task", "task"),
        ("experiment_run", "run"),
        ("experiment_study", "study"),
    ],
)
def test_standalone_document_rejects_versioned_subject_missing_ref_version(subject_kind: str, ref_kind: str) -> None:
    # Closes the replay hole for the standalone/published disclosure form too,
    # not just embedded (carrier) disclosures.
    payload = _structural_disclosure_payload(
        subject_kind=subject_kind,
        subject_ref={"ref_kind": ref_kind, "ref_id": "subject-1"},
    )
    with pytest.raises(ValidationError, match="must include ref_version"):
        ValidationBasisDisclosureDocumentModel.model_validate(
            {"schema_version": "validation-basis-disclosure/v1", "disclosure": payload}
        )


def test_scenario_subject_reference_still_accepts_missing_ref_version() -> None:
    # Regression guard: the id-only scenario kind must not be over-swept by
    # the versioned-kind rule above.
    ref = ValidationSubjectReferenceModel.model_validate({"ref_kind": "scenario", "ref_id": "scenario-1"})
    assert ref.ref_version is None


# --------------------------------------------------------------------------- #
# Real canonicalization-pipeline binding (not a fabricated digest)            #
# --------------------------------------------------------------------------- #


def test_scenario_snapshot_disclosure_binds_to_real_canonical_digest() -> None:
    snapshot = _snapshot()
    digest = canonical_instantiated_sdl_digest(snapshot.scenario).value

    payload = _semantic_disclosure_payload(
        subject_ref={
            "ref_kind": "scenario-snapshot",
            "ref_id": snapshot.scenario.name,
            "ref_digest": digest,
        },
    )
    document = ValidationBasisDisclosureDocumentModel.model_validate(
        {"schema_version": "validation-basis-disclosure/v1", "disclosure": payload}
    )
    assert document.disclosure.subject_ref.ref_digest == digest


def test_scenario_snapshot_disclosure_digest_distinguishes_stale_snapshot_identity() -> None:
    current_snapshot = _snapshot()
    stale_snapshot = _snapshot(_SNAPSHOT_SDL_MUTATED)

    current_digest = canonical_instantiated_sdl_digest(current_snapshot.scenario).value
    stale_digest = canonical_instantiated_sdl_digest(stale_snapshot.scenario).value

    # The mutation changes the instantiated scenario's semantic content, so the
    # two real snapshots must not collide on the same canonical digest -- the
    # whole point of binding by digest instead of by bare id.
    assert current_digest != stale_digest

    current_disclosure = ValidationBasisDisclosureModel.model_validate(
        _semantic_disclosure_payload(
            subject_ref={
                "ref_kind": "scenario-snapshot",
                "ref_id": current_snapshot.scenario.name,
                "ref_digest": current_digest,
            },
        )
    )
    stale_disclosure = ValidationBasisDisclosureModel.model_validate(
        _semantic_disclosure_payload(
            subject_ref={
                "ref_kind": "scenario-snapshot",
                "ref_id": stale_snapshot.scenario.name,
                "ref_digest": stale_digest,
            },
        )
    )

    assert current_disclosure.subject_ref.ref_digest == current_digest
    assert stale_disclosure.subject_ref.ref_digest == stale_digest
    assert current_disclosure.subject_ref.ref_digest != stale_disclosure.subject_ref.ref_digest


def test_generic_scenario_subject_reference_rejects_real_canonical_digest() -> None:
    # The plain "scenario" subject kind is an identity-only (authoring) reference
    # -- unlike scenario-snapshot, it must not accept a digest at all, even one
    # produced by the real canonicalization pipeline rather than a fabricated
    # placeholder.
    scenario = parse_sdl(_SNAPSHOT_SDL)
    real_digest = canonical_sdl_digest(scenario).value
    payload = _structural_disclosure_payload(
        subject_ref={"ref_kind": "scenario", "ref_id": scenario.name, "ref_digest": real_digest}
    )
    with pytest.raises(ValidationError, match="must not carry ref_digest"):
        ValidationBasisDisclosureModel.model_validate(payload)


# --------------------------------------------------------------------------- #
# Gate-row / profile-declared-set failures                                    #
# --------------------------------------------------------------------------- #


def test_disclosure_rejects_duplicate_gate_rows() -> None:
    payload = _structural_disclosure_payload(
        gate_results=[_gate("syntax_validation"), _gate("syntax_validation"), _gate("schema_validation")]
    )
    with pytest.raises(ValidationError, match="unique"):
        ValidationBasisDisclosureModel.model_validate(payload)


def test_disclosure_rejects_missing_required_gate() -> None:
    payload = _structural_disclosure_payload(gate_results=[_gate("syntax_validation"), _gate("schema_validation")])
    with pytest.raises(ValidationError, match="missing required"):
        ValidationBasisDisclosureModel.model_validate(payload)


def test_disclosure_rejects_undeclared_gate_kind() -> None:
    payload = _structural_disclosure_payload(
        gate_results=[*[_gate(kind) for kind in _STRUCTURAL_GATES], _gate("falsification_protocol")]
    )
    with pytest.raises(ValidationError, match="not declared by profile"):
        ValidationBasisDisclosureModel.model_validate(payload)


def test_disclosure_rejects_undeclared_limitation_category() -> None:
    payload = _structural_disclosure_payload(
        limitations=[{"limitation_category": "evidence_withheld", "detail": "n/a for structural"}]
    )
    with pytest.raises(ValidationError, match="not declared by profile"):
        ValidationBasisDisclosureModel.model_validate(payload)


# --------------------------------------------------------------------------- #
# ADR-072 strength ordering -- EACH violation                                 #
# --------------------------------------------------------------------------- #


def test_structural_rows_cannot_claim_semantic_strength() -> None:
    payload = _semantic_disclosure_payload(
        gate_results=[_gate(kind) for kind in _STRUCTURAL_GATES]
        + [_gate("semantic_invariant_validation", outcome="not_run", detail="not evaluated")]
        + [_gate("reference_resolution", outcome="not_run", detail="not evaluated")]
        + [_gate("lifecycle_separation"), _gate("cross_artifact_consistency")],
        limitations=[{"limitation_category": "semantic_only", "detail": "structural rows only"}],
    )
    with pytest.raises(ValidationError, match="requires passed gate rows"):
        ValidationBasisDisclosureModel.model_validate(payload)


def test_semantic_rows_cannot_claim_behavioral_strength() -> None:
    payload = _behavioral_disclosure_payload(
        gate_results=[_gate(kind) for kind in _SEMANTIC_REQUIRED_GATES]
        + [_gate("behavioral_execution", outcome="not_run", detail="no runtime path"), _gate("governed_diagnostics")],
        limitations=[{"limitation_category": "bounded_coverage", "detail": "semantic rows only"}],
    )
    with pytest.raises(ValidationError, match="requires passed gate rows"):
        ValidationBasisDisclosureModel.model_validate(payload)


def test_evidence_backed_requires_at_least_one_evidence_ref() -> None:
    payload = _evidence_backed_disclosure_payload(evidence_refs=[])
    with pytest.raises(ValidationError, match="evidence_ref"):
        ValidationBasisDisclosureModel.model_validate(payload)


def test_falsification_backed_requires_protocol_and_status_passed() -> None:
    payload = _falsification_backed_disclosure_payload(
        gate_results=[_gate(kind) for kind in _EVIDENCE_BACKED_REQUIRED_GATES]
        + [
            _gate("falsification_protocol", outcome="not_run", detail="no protocol bound"),
            _gate("evidence_status", outcome="unknown", detail="status not recorded"),
        ],
        limitations=[{"limitation_category": "bounded_coverage", "detail": "evidence rows only"}],
    )
    with pytest.raises(ValidationError, match="requires passed gate rows"):
        ValidationBasisDisclosureModel.model_validate(payload)


# --------------------------------------------------------------------------- #
# Required-gate failure caps the claim; not_applicable; sub-minimum strength;  #
# audience restriction                                                        #
# --------------------------------------------------------------------------- #


def test_required_gate_failure_requires_explicit_limitation() -> None:
    payload = _structural_disclosure_payload(
        gate_results=[
            _gate("syntax_validation"),
            _gate("schema_validation", outcome="failed"),
            _gate("vocabulary_validation"),
        ],
        achieved_strength="structural",
    )
    # achieved_strength=structural's ADR-072 ordering also requires schema_validation
    # passed, so this case is expected to fail the ordering check first; use a
    # profile whose required gate is not in the ADR-072 minimum set for structural
    # by instead exercising the semantic profile's optional-adjacent required gates.
    payload = _semantic_disclosure_payload(
        gate_results=[_gate(kind) for kind in _SEMANTIC_REQUIRED_GATES[:-1]]
        + [_gate("cross_artifact_consistency", outcome="failed", detail="cross artifact check failed")],
    )
    with pytest.raises(ValidationError, match="explicit limitation"):
        ValidationBasisDisclosureModel.model_validate(payload)

    payload["limitations"] = [{"limitation_category": "bounded_coverage", "detail": "cross-artifact check failed"}]
    disclosure = ValidationBasisDisclosureModel.model_validate(payload)
    assert disclosure.limitations[0].limitation_category == "bounded_coverage"


def test_not_applicable_gate_requires_explicit_limitation() -> None:
    payload = _behavioral_disclosure_payload(
        gate_results=[_gate(kind) for kind in _SEMANTIC_REQUIRED_GATES]
        + [
            _gate("behavioral_execution"),
            _gate("governed_diagnostics", outcome="not_applicable", detail="no diagnostics channel"),
        ],
    )
    with pytest.raises(ValidationError, match="explicit limitation"):
        ValidationBasisDisclosureModel.model_validate(payload)

    payload["limitations"] = [{"limitation_category": "bounded_coverage", "detail": "diagnostics channel absent"}]
    disclosure = ValidationBasisDisclosureModel.model_validate(payload)
    assert disclosure.achieved_strength == "behavioral"


def test_sub_minimum_strength_is_legal_only_with_explicit_limitation() -> None:
    payload = _structural_disclosure_payload(profile_id="raes-semantic-validation")
    with pytest.raises(ValidationError, match="missing required"):
        ValidationBasisDisclosureModel.model_validate(payload)

    payload = _structural_disclosure_payload(
        profile_id="raes-semantic-validation",
        gate_results=[_gate(kind) for kind in _SEMANTIC_REQUIRED_GATES],
        achieved_strength="structural",
    )
    with pytest.raises(ValidationError, match="minimum_strength"):
        ValidationBasisDisclosureModel.model_validate(payload)

    payload["limitations"] = [{"limitation_category": "bounded_coverage", "detail": "below profile minimum"}]
    disclosure = ValidationBasisDisclosureModel.model_validate(payload)
    assert disclosure.achieved_strength == "structural"


def test_audience_restricted_view_requires_audience_restricted_limitation() -> None:
    payload = _evidence_backed_disclosure_payload(audience="public")
    with pytest.raises(ValidationError, match="audience_restricted"):
        ValidationBasisDisclosureModel.model_validate(payload)

    payload["limitations"] = [{"limitation_category": "audience_restricted", "detail": "public view is redacted"}]
    disclosure = ValidationBasisDisclosureModel.model_validate(payload)
    assert disclosure.audience == "public"


def test_audience_restricted_cannot_borrow_a_limitation_category_the_profile_does_not_declare() -> None:
    # The structural profile declares only structural_only/bounded_coverage, so a
    # public structural view cannot borrow the audience_restricted category to
    # satisfy the audience-restriction rule.
    payload = _structural_disclosure_payload(
        audience="public",
        limitations=[
            {
                "limitation_category": "audience_restricted",
                "detail": "Public view omits internal semantic findings.",
            }
        ],
    )
    with pytest.raises(ValidationError, match="not declared by profile"):
        ValidationBasisDisclosureModel.model_validate(payload)


# --------------------------------------------------------------------------- #
# Carrier-embedded disclosures: subject_ref/subject_kind must match carrier    #
# --------------------------------------------------------------------------- #


def _task_payload_with_disclosures(disclosures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "experiment-task/v1",
        "task_id": "task-1",
        "task_version": "v1",
        "title": "Task",
        "description": "Task description",
        "scenario_ref": {"ref_kind": "scenario", "ref_id": "scenario-1"},
        "evaluation_protocol": {
            "protocol_id": "protocol-1",
            "protocol_version": "v1",
            "intent": "measure",
            "unit_of_analysis": "run",
            "metric_definitions": {
                "metric-1": {
                    "metric_id": "metric-1",
                    "metric_version": "v1",
                    "name": "Metric",
                    "measured_construct": "construct",
                    "unit_of_analysis": "run",
                    "value_kind": "boolean",
                    "direction": "higher-is-better",
                    "evidence_requirements": [{"ref_kind": "evidence", "ref_id": "req-1"}],
                }
            },
            "observation_requirements": [{"ref_kind": "evidence", "ref_id": "req-1"}],
        },
        "intended_use": "testing",
        "population_or_construct": "construct",
        "split_and_leakage_controls": {"partitioning_strategy": "n/a"},
        "apparatus_constraints": {"notes": ["none"]},
        "validity_notes": [{"category": "other", "note": "n/a"}],
        "artifact_refs": [
            {
                "artifact_id": "artifact-1",
                "role": "protocol",
                "media_type": "application/json",
                "uri": "urn:artifact:1",
                "checksum": {"algorithm": "sha256", "value": "a" * 64},
                "size_bytes": 1,
                "created_at": "2026-07-24T00:00:00Z",
                "source": "authoring",
                "sensitivity": "internal",
            }
        ],
        "validation_basis_disclosures": disclosures,
    }


def test_experiment_task_accepts_matching_validation_basis_disclosure() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_task",
        subject_ref={"ref_kind": "task", "ref_id": "task-1", "ref_version": "v1"},
    )
    task = ExperimentTaskModel.model_validate(_task_payload_with_disclosures([disclosure_payload]))
    assert len(task.validation_basis_disclosures) == 1


def test_experiment_task_rejects_disclosure_with_mismatched_subject_ref() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_task",
        subject_ref={"ref_kind": "task", "ref_id": "some-other-task", "ref_version": "v1"},
    )
    carrier_payload = _task_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must match the carrier"):
        ExperimentTaskModel.model_validate(carrier_payload)


def test_experiment_task_rejects_disclosure_missing_ref_version() -> None:
    # The exact replay hole from the security review: correct ref_id, no
    # ref_version at all. Caught at the reference-model layer before the
    # carrier identity check even runs.
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_task",
        subject_ref={"ref_kind": "task", "ref_id": "task-1"},
    )
    carrier_payload = _task_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must include ref_version"):
        ExperimentTaskModel.model_validate(carrier_payload)


def test_experiment_task_rejects_disclosure_with_wrong_ref_version() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_task",
        subject_ref={"ref_kind": "task", "ref_id": "task-1", "ref_version": "v2"},
    )
    carrier_payload = _task_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must match the carrier"):
        ExperimentTaskModel.model_validate(carrier_payload)


def test_experiment_task_rejects_disclosure_with_mismatched_subject_kind() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="scenario",
        subject_ref={"ref_kind": "scenario", "ref_id": "scenario-1"},
    )
    carrier_payload = _task_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must match the carrier"):
        ExperimentTaskModel.model_validate(carrier_payload)


_RUN_REFERENCE_FIXTURE = REPO_ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json"
_STUDY_REFERENCE_FIXTURE = REPO_ROOT / "contracts/fixtures/experiment-core/experiment-study-v1/valid/reference.json"


def _run_payload_with_disclosures(disclosures: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.loads(_RUN_REFERENCE_FIXTURE.read_text(encoding="utf-8"))
    payload["validation_basis_disclosures"] = disclosures
    return payload


def _study_payload_with_disclosures(disclosures: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.loads(_STUDY_REFERENCE_FIXTURE.read_text(encoding="utf-8"))
    payload["validation_basis_disclosures"] = disclosures
    return payload


def test_experiment_run_accepts_matching_validation_basis_disclosure() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_run",
        subject_ref={"ref_kind": "run", "ref_id": "run-techvault-001", "ref_version": "1.0.0"},
    )
    run = ExperimentRunModel.model_validate(_run_payload_with_disclosures([disclosure_payload]))
    assert len(run.validation_basis_disclosures) == 1


def test_experiment_run_rejects_disclosure_with_mismatched_subject_ref() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_run",
        subject_ref={"ref_kind": "run", "ref_id": "some-other-run", "ref_version": "1.0.0"},
    )
    carrier_payload = _run_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must match the carrier"):
        ExperimentRunModel.model_validate(carrier_payload)


def test_experiment_run_rejects_disclosure_missing_ref_version() -> None:
    # The exact replay hole from the security review: correct ref_id, no
    # ref_version at all. Caught at the reference-model layer before the
    # carrier identity check even runs.
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_run",
        subject_ref={"ref_kind": "run", "ref_id": "run-techvault-001"},
    )
    carrier_payload = _run_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must include ref_version"):
        ExperimentRunModel.model_validate(carrier_payload)


def test_experiment_run_rejects_disclosure_with_wrong_ref_version() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_run",
        subject_ref={"ref_kind": "run", "ref_id": "run-techvault-001", "ref_version": "9.9.9"},
    )
    carrier_payload = _run_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must match the carrier"):
        ExperimentRunModel.model_validate(carrier_payload)


def test_experiment_run_rejects_disclosure_with_mismatched_subject_kind() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="scenario",
        subject_ref={"ref_kind": "scenario", "ref_id": "scenario-1"},
    )
    carrier_payload = _run_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must match the carrier"):
        ExperimentRunModel.model_validate(carrier_payload)


def test_experiment_study_accepts_matching_validation_basis_disclosure() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_study",
        subject_ref={"ref_kind": "study", "ref_id": "study-techvault-baseline", "ref_version": "1.0.0"},
    )
    study = ExperimentStudyModel.model_validate(_study_payload_with_disclosures([disclosure_payload]))
    assert len(study.validation_basis_disclosures) == 1


def test_experiment_study_rejects_disclosure_with_mismatched_subject_ref() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_study",
        subject_ref={"ref_kind": "study", "ref_id": "some-other-study", "ref_version": "1.0.0"},
    )
    carrier_payload = _study_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must match the carrier"):
        ExperimentStudyModel.model_validate(carrier_payload)


def test_experiment_study_rejects_disclosure_missing_ref_version() -> None:
    # The exact replay hole from the security review: correct ref_id, no
    # ref_version at all. Caught at the reference-model layer before the
    # carrier identity check even runs.
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_study",
        subject_ref={"ref_kind": "study", "ref_id": "study-techvault-baseline"},
    )
    carrier_payload = _study_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must include ref_version"):
        ExperimentStudyModel.model_validate(carrier_payload)


def test_experiment_study_rejects_disclosure_with_wrong_ref_version() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="experiment_study",
        subject_ref={"ref_kind": "study", "ref_id": "study-techvault-baseline", "ref_version": "9.9.9"},
    )
    carrier_payload = _study_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must match the carrier"):
        ExperimentStudyModel.model_validate(carrier_payload)


def test_experiment_study_rejects_disclosure_with_mismatched_subject_kind() -> None:
    disclosure_payload = _structural_disclosure_payload(
        subject_kind="scenario",
        subject_ref={"ref_kind": "scenario", "ref_id": "scenario-1"},
    )
    carrier_payload = _study_payload_with_disclosures([disclosure_payload])
    with pytest.raises(ValidationError, match="must match the carrier"):
        ExperimentStudyModel.model_validate(carrier_payload)


# --------------------------------------------------------------------------- #
# Fixture-corpus conformance                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("fixture", "valid"),
    [
        ("valid/structural-scenario.json", True),
        ("valid/evidence-backed-run.json", True),
        ("valid/scenario-snapshot.json", True),
        ("invalid/unknown-profile.json", False),
        ("invalid/missing-required-gate.json", False),
        ("invalid/scenario-snapshot-missing-digest.json", False),
        ("invalid/run-missing-ref-version.json", False),
    ],
)
def test_published_disclosure_fixtures_use_conformance_validation(fixture: str, valid: bool) -> None:
    path = FIXTURES_ROOT / fixture
    diagnostics = _fixture_case_diagnostics(
        "validation-basis-disclosure-v1",
        json.loads(path.read_text(encoding="utf-8")),
    )
    assert (not diagnostics) is valid


def test_disclosure_schema_is_published_with_governed_invariants() -> None:
    schema = schema_bundle()["validation-basis-disclosure-v1"]
    published = json.loads(
        (REPO_ROOT / "contracts/schemas/profiles/validation-basis-disclosure-v1.json").read_text(encoding="utf-8")
    )
    assert published == schema
    invariant_ids = {item["id"] for item in schema["$defs"]["ValidationBasisDisclosureModel"]["x-raes-invariants"]}
    assert "validation-basis-profile-join-resolves" in invariant_ids


def test_deepcopy_of_payload_is_not_mutated_by_validation() -> None:
    # Regression guard: constructing a disclosure must not mutate the caller's
    # source payload dict (defensive-copy hygiene used across the suite).
    payload = _structural_disclosure_payload()
    original = deepcopy(payload)
    ValidationBasisDisclosureModel.model_validate(payload)
    assert payload == original

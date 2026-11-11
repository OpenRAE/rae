"""SEM-224 observability plane separation semantics.

ADR-066 and ``specs/formal/observability-evidence-plane.md`` define five named
observability/evidence planes and require a carrier-oriented plane classifier
plus portable traceability over them (issue #334). The plane separation itself
is realised by the existing experiment-core and participant carriers; this
module proves the *unifying* obligations #334 owns:

- OE-01: every claim-bearing observability/evidence carrier has exactly one
  primary plane;
- OE-11: a bare string (``log``, ``trace``, ``telemetry``, ``observation``,
  ``evidence``) never decides plane ownership -- the carrier role does;
- the three claim-bearing experiment-core contracts publish their plane as a
  portable ``x-raes-plane`` annotation; and
- the five distinctions hold end-to-end (reusing the EXP-707/708/709 structural
  rules and the SEM-216 boundary fixtures where they already cover a probe).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes._runtime_service_families import RUNTIME_SERVICE_FAMILIES
from raes.observability_plane_semantics import (
    AMBIGUOUS_PLANE_TOKENS,
    SCENARIO_NATIVE_OBSERVABILITY_FAMILIES,
    _validate_scenario_native_families,
    assert_single_primary_plane,
    classify_runtime_family,
    token_decides_plane,
)
from raes_contracts.contracts import ExperimentDerivedMeasureModel, ExperimentEvidenceRecordModel
from raes_contracts.observability_planes import (
    PLANE_BY_CONTRACT_ID,
    ObservabilityEvidencePlane,
    classify_contract_plane,
)
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_ROOT = REPO_ROOT / "contracts" / "fixtures"
EVIDENCE_RECORD_DIR = FIXTURES_ROOT / "experiment-core" / "experiment-evidence-record-v1"
DERIVED_MEASURE_DIR = FIXTURES_ROOT / "experiment-core" / "experiment-derived-measure-v1"
CONTEXT_VIEW_DIR = FIXTURES_ROOT / "control-plane" / "participant-context-view-v1"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_schema_and_model_reject(contract_id: str, model_cls, payload: dict) -> None:
    validator = Draft202012Validator(schema_bundle()[contract_id])
    assert list(validator.iter_errors(payload)), f"{contract_id} schema unexpectedly accepted {payload}"
    with pytest.raises(ValidationError):
        model_cls.model_validate(payload)


# --- OE-01: one primary plane per claim-bearing carrier ---------------------


def test_each_claim_bearing_contract_maps_to_exactly_one_plane():
    # The three experiment-core carriers each own exactly one of the five planes.
    assert classify_contract_plane("experiment-capture-spec-v1") is (
        ObservabilityEvidencePlane.AUTHORED_EVIDENCE_REQUIREMENT
    )
    assert classify_contract_plane("experiment-evidence-record-v1") is (ObservabilityEvidencePlane.CAPTURED_EVIDENCE)
    assert classify_contract_plane("experiment-derived-measure-v1") is (ObservabilityEvidencePlane.DERIVED_ANALYSIS)
    # No carrier is registered under two planes.
    assert len(set(PLANE_BY_CONTRACT_ID.values())) >= 4
    for contract_id, plane in PLANE_BY_CONTRACT_ID.items():
        assert isinstance(plane, ObservabilityEvidencePlane), contract_id


def test_assert_single_primary_plane_rejects_zero_or_multiple():
    plane = assert_single_primary_plane(
        [ObservabilityEvidencePlane.CAPTURED_EVIDENCE, ObservabilityEvidencePlane.CAPTURED_EVIDENCE]
    )
    assert plane is ObservabilityEvidencePlane.CAPTURED_EVIDENCE
    with pytest.raises(ValueError):
        assert_single_primary_plane([])
    with pytest.raises(ValueError):
        assert_single_primary_plane(
            [ObservabilityEvidencePlane.CAPTURED_EVIDENCE, ObservabilityEvidencePlane.DERIVED_ANALYSIS]
        )


def test_classify_contract_plane_fails_closed_on_unknown_carrier():
    # Plane ownership comes from a registered carrier role, never a guess.
    with pytest.raises(ValueError):
        classify_contract_plane("some-unregistered-contract-v9")


# --- OE-11: a bare string never decides plane ownership ---------------------


def test_token_never_decides_plane():
    for token in AMBIGUOUS_PLANE_TOKENS:
        assert token_decides_plane(token) is False
    # OE-11 is universal: no string decides a plane, including a registered
    # contract id or an arbitrary unknown string -- only the carrier role does.
    assert token_decides_plane("experiment-capture-spec-v1") is False
    assert token_decides_plane("some-unknown-string") is False
    # The vocabulary the ADR calls out as ambiguous is covered.
    assert {"log", "trace", "telemetry", "observation", "evidence"} <= AMBIGUOUS_PLANE_TOKENS


# --- Distinction 1: scenario-native observability is an SDL runtime family ---


def test_scenario_native_observability_families_are_registered_and_distinct():
    registered = {family.collection_name for family in RUNTIME_SERVICE_FAMILIES}
    assert SCENARIO_NATIVE_OBSERVABILITY_FAMILIES, "scenario-native family set must be non-empty"
    assert SCENARIO_NATIVE_OBSERVABILITY_FAMILIES.issubset(registered)
    for collection_name in SCENARIO_NATIVE_OBSERVABILITY_FAMILIES:
        assert classify_runtime_family(collection_name) is (ObservabilityEvidencePlane.SCENARIO_NATIVE_OBSERVABILITY)


def test_scenario_native_family_validation_fails_closed_on_unregistered_name():
    # A scenario-native family that is not in the runtime-family registry must
    # raise at construction time rather than silently misclassify.
    with pytest.raises(RuntimeError, match="not registered"):
        _validate_scenario_native_families(("not_a_real_family",), frozenset({"service_listeners"}))
    # The happy path returns the validated set unchanged.
    assert _validate_scenario_native_families(
        ("service_listeners",), frozenset({"service_listeners", "applications"})
    ) == frozenset({"service_listeners"})


def test_backend_observability_is_not_a_participant_observation():
    # SEM-216 B5 fixture: a backend observability stream presented as a portable
    # participant observation is rejected -- the scenario-native plane is not the
    # processor/backend operational plane.
    from raes_contracts.contracts import ParticipantContextViewModel

    payload = _load(CONTEXT_VIEW_DIR / "invalid" / "sem216-backend-observability-as-observation.json")
    _assert_schema_and_model_reject("participant-context-view-v1", ParticipantContextViewModel, payload)


# --- Distinction 2: authored evidence requirement is not proof of capture ---


def test_capture_spec_and_evidence_record_are_different_planes():
    assert classify_contract_plane("experiment-capture-spec-v1") is not (
        classify_contract_plane("experiment-evidence-record-v1")
    )


def test_capture_record_without_requirement_ref_is_rejected():
    # OE-04: a raw capture record cannot claim authored-requirement satisfaction
    # with no requirement reference.
    payload = _load(EVIDENCE_RECORD_DIR / "invalid" / "sem224-capture-record-without-requirement-ref.json")
    assert "capture_requirement_ref" not in payload
    _assert_schema_and_model_reject("experiment-evidence-record-v1", ExperimentEvidenceRecordModel, payload)


# --- Distinction 3: processor/backend operational observability -------------


def test_operational_carriers_map_to_processor_backend_plane():
    for contract_id in ("backend-manifest-v2", "processor-manifest-v2", "experiment-apparatus-context-v1"):
        assert classify_contract_plane(contract_id) is (ObservabilityEvidencePlane.PROCESSOR_BACKEND_OPERATIONAL)


# --- Distinction 4: captured evidence is not derived analysis ---------------


def test_derived_analysis_is_not_captured_evidence():
    # SEM-216 B3 fixture: a derived-measure shape (measure_kind/value) presented
    # as a raw evidence record is rejected.
    payload = _load(EVIDENCE_RECORD_DIR / "invalid" / "sem216-analysis-output-as-evidence.json")
    _assert_schema_and_model_reject("experiment-evidence-record-v1", ExperimentEvidenceRecordModel, payload)
    assert classify_contract_plane("experiment-evidence-record-v1") is not (
        classify_contract_plane("experiment-derived-measure-v1")
    )


# --- Distinction 5: derived analysis must cite source evidence (OE-06) ------


def test_derived_measure_without_source_evidence_is_rejected():
    payload = _load(DERIVED_MEASURE_DIR / "invalid" / "missing-source-evidence.json")
    _assert_schema_and_model_reject("experiment-derived-measure-v1", ExperimentDerivedMeasureModel, payload)


def test_reference_derived_measure_cites_source_evidence():
    payload = _load(DERIVED_MEASURE_DIR / "valid" / "reference.json")
    Draft202012Validator(schema_bundle()["experiment-derived-measure-v1"]).validate(payload)
    model = ExperimentDerivedMeasureModel.model_validate(payload)
    assert model.source_evidence_refs, "a derived measure must cite at least one source evidence record"


# --- Portable plane traceability published on the three carriers ------------


def test_claim_bearing_contracts_publish_their_plane_annotation():
    bundle = schema_bundle()
    expected = {
        "experiment-capture-spec-v1": ObservabilityEvidencePlane.AUTHORED_EVIDENCE_REQUIREMENT.value,
        "experiment-evidence-record-v1": ObservabilityEvidencePlane.CAPTURED_EVIDENCE.value,
        "experiment-derived-measure-v1": ObservabilityEvidencePlane.DERIVED_ANALYSIS.value,
    }
    for contract_id, plane_value in expected.items():
        assert bundle[contract_id].get("x-raes-plane") == plane_value, contract_id

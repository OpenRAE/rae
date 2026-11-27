"""SEM-216 boundary semantics: explicit distinction between runtime-observable
state, captured evidence, derived evaluations, analysis outputs, and
audience-specific views.

Each test names one of the five cross-stratum boundary obligations (B1-B5) and
proves the violation is rejected by BOTH the published JSON Schema and the
closed-world Pydantic model, with a positive case proving the legitimate
mediated view is admitted. SEM-216 is enforced over the existing contract
families (no super-schema); see
``docs/decisions/issue-248-sem-216-boundary-semantics-preflight.md`` and the
``## SEM-216`` section of
``specs/formal/participant-semantics/README.md``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.contracts import ExperimentEvidenceRecordModel, ParticipantContextViewModel
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_ROOT = REPO_ROOT / "contracts" / "fixtures"
CONTEXT_VIEW_DIR = FIXTURES_ROOT / "control-plane" / "participant-context-view-v1"
EVIDENCE_RECORD_DIR = FIXTURES_ROOT / "experiment-core" / "experiment-evidence-record-v1"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_schema_and_model_reject(contract_id: str, model_cls, payload: dict) -> None:
    validator = Draft202012Validator(schema_bundle()[contract_id])
    assert list(validator.iter_errors(payload)), f"{contract_id} schema unexpectedly accepted {payload}"
    with pytest.raises(ValidationError):
        model_cls.model_validate(payload)


# --- B1: archived evidence cannot become participant-visible without a view rule ---


def test_b1_archival_evidence_participant_visible_without_view_rule_is_rejected():
    payload = _load(CONTEXT_VIEW_DIR / "invalid" / "sem216-archival-evidence-participant-visible.json")
    assert payload["audience_scope"] == "participant_visible"
    assert any(layer["source_layer"] == "evidence_record" for layer in payload["source_layers"])
    assert "derivation_basis_ref" not in payload
    _assert_schema_and_model_reject("participant-context-view-v1", ParticipantContextViewModel, payload)


# --- B2: hidden adjudication / evaluation output cannot reach a participant view
#         without a redaction policy governing the disclosure ---


def test_b2_hidden_adjudication_in_evaluation_output_without_redaction_policy_is_rejected():
    payload = _load(CONTEXT_VIEW_DIR / "invalid" / "sem216-hidden-adjudication-in-evaluation-output.json")
    assert payload["audience_scope"] == "participant_visible"
    assert any(layer["source_layer"] == "derived_measure" for layer in payload["source_layers"])
    assert "redaction_policy_ref" not in payload
    _assert_schema_and_model_reject("participant-context-view-v1", ParticipantContextViewModel, payload)


# --- B3: derived analysis is never captured evidence ---


def test_b3_derived_analysis_as_captured_evidence_is_rejected():
    payload = _load(EVIDENCE_RECORD_DIR / "invalid" / "sem216-analysis-output-as-evidence.json")
    # Carries derived-measure shape (measure_kind / value) that an evidence record must not hold.
    assert payload.get("measure_kind") == "score"
    _assert_schema_and_model_reject("experiment-evidence-record-v1", ExperimentEvidenceRecordModel, payload)


# --- B4: evidence claims must disclose redaction/loss ---


def test_b4_withheld_evidence_without_loss_disclosure_is_rejected():
    payload = _load(EVIDENCE_RECORD_DIR / "invalid" / "sem216-withheld-without-loss-disclosure.json")
    assert payload["redaction_state"] == "withheld"
    assert "loss_disclosure" not in payload["raw_content"]
    _assert_schema_and_model_reject("experiment-evidence-record-v1", ExperimentEvidenceRecordModel, payload)


# --- B5: backend observability is not a portable semantic observation ---


def test_b5_backend_observability_as_portable_observation_is_rejected():
    payload = _load(CONTEXT_VIEW_DIR / "invalid" / "sem216-backend-observability-as-observation.json")
    assert any(layer["source_layer"] == "backend_observability_stream" for layer in payload["source_layers"])
    _assert_schema_and_model_reject("participant-context-view-v1", ParticipantContextViewModel, payload)


# --- Positive: a participant-visible view that correctly mediates an archived
#     evidence record through a governed view rule + redaction policy is admitted ---


def test_mediated_participant_visible_evidence_view_is_accepted():
    payload = _load(CONTEXT_VIEW_DIR / "valid" / "sem216-mediated-evidence-view.json")
    Draft202012Validator(schema_bundle()["participant-context-view-v1"]).validate(payload)
    model = ParticipantContextViewModel.model_validate(payload)
    assert model.audience_scope == "participant_visible"
    assert model.derivation_basis_ref is not None
    assert model.redaction_policy_ref is not None
    archival = [layer for layer in model.source_layers if layer.source_layer in {"evidence_record", "derived_measure"}]
    assert archival, "fixture must exercise an archival source layer"
    for layer in archival:
        assert layer.source_id in model.transformation.input_source_ids


# --- Relational mediation rule (model-side): an archival source layer that is
#     present in a participant-visible view but NOT consumed by the transformation
#     view rule is rejected even when derivation_basis_ref and redaction_policy_ref
#     are both declared. ---


def test_unmediated_archival_source_layer_is_rejected_model_side():
    payload = _load(CONTEXT_VIEW_DIR / "valid" / "sem216-mediated-evidence-view.json")
    unmediated = copy.deepcopy(payload)
    unmediated["transformation"]["input_source_ids"] = [
        source_id
        for source_id in unmediated["transformation"]["input_source_ids"]
        if source_id != "evidence-archive-0001"
    ]
    with pytest.raises(ValidationError, match="mediated"):
        ParticipantContextViewModel.model_validate(unmediated)


# --- B1/B2 payload boundary (model-side): a participant-visible view must not alias
#     payload_ref to a raw archival evidence/measure ref even when the source is
#     mediated and the governance refs are present, or the consumer can resolve raw
#     archived evidence instead of the redacted view output. ---


def test_payload_ref_aliasing_raw_archival_source_is_rejected_model_side():
    payload = _load(CONTEXT_VIEW_DIR / "valid" / "sem216-mediated-evidence-view.json")
    aliased = copy.deepcopy(payload)
    aliased["payload_ref"] = "evidence.archive.blue.0001"  # the raw evidence_record source ref
    with pytest.raises(ValidationError, match="payload_ref"):
        ParticipantContextViewModel.model_validate(aliased)


def test_view_schema_publishes_sem216_relational_invariants():
    # The relational obligations that JSON Schema cannot express are still part of the published
    # portable contract via x-raes-invariants, so the documented boundary is not model-only.
    schema = schema_bundle()["participant-context-view-v1"]
    invariant_ids = {entry["id"] for entry in schema.get("x-raes-invariants", [])}
    assert "context-view-sem216-archival-source-mediated" in invariant_ids
    assert "context-view-sem216-payload-not-raw-archival" in invariant_ids

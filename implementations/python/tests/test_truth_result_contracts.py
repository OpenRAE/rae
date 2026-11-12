"""Portable proposition truth-result contracts for issue #725."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError
from raes_contracts.contracts import PropositionTruthResultModel
from raes_schemas import schema_bundle


def _observed_result() -> dict[str, object]:
    return {
        "schema_version": "proposition-truth-result/v1",
        "result_id": "truth-run-42-service-ready",
        "proposition_address": "evaluation.proposition.service-available",
        "assertion_address": "evaluation.assertion.service-ready",
        "assertion_polarity": "positive",
        "proposition_outcome": "true",
        "assertion_outcome": "true",
        "evaluation_basis": "observed_state",
        "indeterminacy_reason": None,
        "probe_binding": {
            "binding_id": "http-probe-binding",
            "implementation_id": "example/http-health-probe",
            "implementation_version": "2.1.0",
            "artifact_digest": "sha256:" + "a" * 64,
            "backend_manifest_ref": "backend-manifest:range-a",
            "proposition_address": "evaluation.proposition.service-available",
            "capability_refs": ["predicate.string.equals", "evidence.log"],
        },
        "evidence_refs": ["experiment-evidence:run-42/http-health"],
        "declared_artifact_digest": None,
        "temporal_context": {
            "boundary_ref": "objectives.restore-service:completion",
            "time_domain": "scenario_time",
            "clock_authority": "experiment-clock:run-42",
        },
        "loss_disclosures": [],
        "unsupported_capability_refs": [],
    }


def test_observed_decision_requires_binding_evidence_and_governed_time_context() -> None:
    result = PropositionTruthResultModel.model_validate(_observed_result())

    assert result.proposition_outcome.value == "true"
    assert result.assertion_outcome.value == "true"
    assert result.probe_binding is not None
    assert result.probe_binding.artifact_digest.startswith("sha256:")


@pytest.mark.parametrize("field", ["probe_binding", "temporal_context"])
def test_observed_decision_rejects_missing_realization_context(field: str) -> None:
    payload = _observed_result()
    payload[field] = None
    with pytest.raises(ValidationError, match=field):
        PropositionTruthResultModel.model_validate(payload)


def test_observed_decision_rejects_missing_evidence() -> None:
    payload = _observed_result()
    payload["evidence_refs"] = []
    with pytest.raises(ValidationError, match="evidence_refs"):
        PropositionTruthResultModel.model_validate(payload)


def test_negative_assertion_must_invert_only_decided_truth() -> None:
    payload = _observed_result()
    payload["assertion_polarity"] = "negative"
    payload["assertion_outcome"] = "false"
    assert PropositionTruthResultModel.model_validate(payload).assertion_outcome.value == "false"

    payload["assertion_outcome"] = "true"
    with pytest.raises(ValidationError, match="negative assertion outcome"):
        PropositionTruthResultModel.model_validate(payload)


def test_unknown_result_preserves_typed_conflicting_evidence_reason() -> None:
    payload = _observed_result()
    payload.update(
        proposition_outcome="unknown",
        assertion_outcome="unknown",
        indeterminacy_reason="conflicting_evidence",
        loss_disclosures=[{"kind": "conflicting", "within_admissible_bound": False}],
    )

    result = PropositionTruthResultModel.model_validate(payload)
    assert result.indeterminacy_reason.value == "conflicting_evidence"


def test_unsupported_is_capability_disposition_not_false_or_unknown() -> None:
    payload = _observed_result()
    payload.update(
        proposition_outcome="unsupported",
        assertion_outcome="unsupported",
        indeterminacy_reason=None,
        probe_binding=None,
        evidence_refs=[],
        temporal_context=None,
        unsupported_capability_refs=["predicate.number.less_than_or_equal"],
    )

    result = PropositionTruthResultModel.model_validate(payload)
    assert result.assertion_outcome.value == "unsupported"
    assert result.unsupported_capability_refs == ["predicate.number.less_than_or_equal"]


def test_lossy_evidence_cannot_decide_truth_outside_admitted_bound() -> None:
    payload = _observed_result()
    payload["loss_disclosures"] = [{"kind": "lossy", "within_admissible_bound": False}]
    with pytest.raises(ValidationError, match="outside the admitted bound"):
        PropositionTruthResultModel.model_validate(payload)


def test_distinct_backend_bindings_preserve_equivalent_semantic_results() -> None:
    left = PropositionTruthResultModel.model_validate(_observed_result())
    right_payload = deepcopy(_observed_result())
    right_payload["probe_binding"] = {
        "binding_id": "agentless-api-binding",
        "implementation_id": "example/range-api-observer",
        "implementation_version": "7.0.3",
        "artifact_digest": "sha256:" + "b" * 64,
        "backend_manifest_ref": "backend-manifest:range-b",
        "proposition_address": "evaluation.proposition.service-available",
        "capability_refs": ["predicate.string.equals", "evidence.api-response"],
    }
    right_payload["evidence_refs"] = ["experiment-evidence:run-42/range-api-health"]
    right = PropositionTruthResultModel.model_validate(right_payload)

    assert left.semantic_claim() == right.semantic_claim()
    assert left.probe_binding != right.probe_binding


def test_truth_result_schema_is_published_by_the_reference_generator() -> None:
    schema = schema_bundle()["proposition-truth-result-v1"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == "proposition-truth-result/v1"

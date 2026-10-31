"""API-423 participant-crossing policy and evidence contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_conformance.conformance.validators import validate_contract_payload
from raes_contracts.contracts import (
    ParticipantCrossingOccurrenceModel,
    validate_participant_crossing_occurrence_context,
)
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingBackendPosture,
    ParticipantCrossingDecisionDisposition,
    ParticipantCrossingDirection,
    ParticipantCrossingGateDisposition,
    ParticipantCrossingInteractionKind,
    ParticipantCrossingLossKind,
    ParticipantCrossingOperation,
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectKind,
    ParticipantCrossingSubjectReferenceModel,
)
from raes_contracts.controlled_vocabularies import load_controlled_vocabulary_catalog
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ID = "participant-crossing-occurrence-v1"
KNOWN_EVIDENCE_REFS = {
    "evidence:crossing-1",
    "evidence-requirement:crossing-decision",
}
KNOWN_AUTHORITY_BASIS_REFS = {
    "authority:red-team",
    "authority:declassification",
}


def _subject(
    *,
    kind: str = "participant-control-occurrence",
    contract_id: str = "participant-control-occurrence-v1",
    ref: str = "control-occurrence.proposal.1",
    revision: str = "1",
) -> dict[str, object]:
    return {
        "subject_kind": kind,
        "contract_id": contract_id,
        "subject_ref": ref,
        "subject_revision": revision,
        "participant_address": "participants.red.operator",
        "episode_id": "episode-1",
    }


def _policy() -> dict[str, object]:
    return {
        "policy_id": "participant-crossing-policy:red",
        "policy_revision": "revision-3",
        "policy_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "policy_decision_ref": "participant-crossing-policy-decision:red:episode-1:8",
        "decision_cut_ref": "participant-policy-cut:red:episode-1:8",
        "effective_order": 8,
        "valid_from_order": 8,
        "valid_until_order": 20,
    }


def _envelope(occurrence: dict[str, object]) -> dict[str, object]:
    return {
        "event_id": f"crossing-occurrence.{occurrence['stage']}.1",
        "schema_name": "participant-crossing-occurrence",
        "schema_version": "1.0.0",
        "event_type": "participant-crossing-occurrence",
        "extension_policy": "closed",
        "participant_address": "participants.red.operator",
        "episode_id": "episode-1",
        "occurred_at": "2026-07-26T08:00:00Z",
        "recorded_at": "2026-07-26T08:00:01Z",
        "ingested_at": "2026-07-26T08:00:02Z",
        "clock_authority": "clock.logical",
        "ordering_basis": "logical_clock",
        "logical_order_ref": "order:10",
        "actor_ref": "controller.human.red",
        "producer_ref": "participant-runtime.red",
        "provenance_refs": ["provenance:crossing-1"],
        "evidence_refs": ["evidence:crossing-1"],
        "object_marking_refs": ["marking:participant-control"],
        "authorization_scope": "scope:red-team",
        "occurrence": {
            "direction": "ingress",
            "interaction_kind": "action-proposal",
            "audience_scope_ref": "audience:red-operator",
            "subject": _subject(),
            "controller_ref": "controller.human.red",
            "authority_basis_refs": ["authority:red-team"],
            "policy": _policy(),
            "effective_order": 10,
            "order_model": "logical_clock",
            "backend_posture": "exact",
            "loss_and_limitations": ["limitation:contract-only"],
            **occurrence,
        },
    }


def _request() -> ParticipantCrossingOccurrenceModel:
    return ParticipantCrossingOccurrenceModel.model_validate(
        _envelope(
            {
                "stage": "requested",
                "request_id": "crossing-request.1",
                "requested_operation": "admission",
                "action_or_projection_ref": "action-contract:contain-host",
                "required_evidence_refs": ["evidence-requirement:crossing-decision"],
            }
        )
    )


def _decision(
    request: ParticipantCrossingOccurrenceModel,
    *,
    disposition: str = "permit",
    gate_override: tuple[str, str] | None = None,
    required_operation: str | None = None,
) -> ParticipantCrossingOccurrenceModel:
    gates = {
        "caller_authorization": "permit",
        "target_authorization": "permit",
        "participant_authority": "permit",
        "action_admission": "permit",
        "visibility": "permit",
        "marking_authorization": "permit",
        "declassification": "not-applicable",
        "backend_support": "permit",
        "transformation_validity": "not-applicable",
    }
    if gate_override is not None:
        gates[gate_override[0]] = gate_override[1]
    value = _envelope(
        {
            "stage": "decided",
            "request_ref": "crossing-request.1",
            "decision_id": "crossing-decision.1",
            "decision_revision": 1,
            "gates": gates,
            "disposition": disposition,
            "reason_code": "policy-satisfied",
            "required_evidence_refs": ["evidence-requirement:crossing-decision"],
            **({"required_operation": required_operation} if required_operation is not None else {}),
        }
    )
    value["event_id"] = "crossing-occurrence.decided.1"
    value["predecessor_event_refs"] = [request.event_id]
    value["occurrence"]["effective_order"] = 11
    return ParticipantCrossingOccurrenceModel.model_validate(value)


def _attempt(
    decision: ParticipantCrossingOccurrenceModel,
    *,
    decision_ref: str = "crossing-decision.1",
    owning_occurrence_ref: str = "control-occurrence.proposal.1",
    disposition: str = "attempted",
) -> ParticipantCrossingOccurrenceModel:
    value = _envelope(
        {
            "stage": "delivery-attempted",
            "decision_ref": decision_ref,
            "attempt_id": "crossing-attempt.1",
            "owning_occurrence_ref": owning_occurrence_ref,
            "disposition": disposition,
        }
    )
    value["event_id"] = "crossing-occurrence.delivery-attempted.1"
    value["predecessor_event_refs"] = [decision.event_id]
    value["occurrence"]["effective_order"] = 12
    return ParticipantCrossingOccurrenceModel.model_validate(value)


def _delivery(
    attempt: ParticipantCrossingOccurrenceModel,
    *,
    decision_ref: str = "crossing-decision.1",
    disposition: str = "delivered",
) -> ParticipantCrossingOccurrenceModel:
    value = _envelope(
        {
            "stage": "delivered",
            "decision_ref": decision_ref,
            "attempt_ref": "crossing-attempt.1",
            "delivery_id": "crossing-delivery.1",
            "owning_occurrence_ref": "control-occurrence.proposal.1",
            "delivery_order": 13,
            "disposition": disposition,
        }
    )
    value["event_id"] = "crossing-occurrence.delivered.1"
    value["predecessor_event_refs"] = [attempt.event_id]
    value["occurrence"]["effective_order"] = 13
    return ParticipantCrossingOccurrenceModel.model_validate(value)


def _validate_context(
    records: list[ParticipantCrossingOccurrenceModel],
    *,
    subject_values: list[dict[str, object]] | None = None,
    policy_values: list[dict[str, object]] | None = None,
    known_evidence_refs: set[str] | None = None,
) -> None:
    subjects = [_subject()] if subject_values is None else subject_values
    policies = [_policy()] if policy_values is None else policy_values
    evidence_refs = KNOWN_EVIDENCE_REFS if known_evidence_refs is None else known_evidence_refs
    validate_participant_crossing_occurrence_context(
        records,
        known_subjects=[ParticipantCrossingSubjectReferenceModel.model_validate(subject) for subject in subjects],
        policies=[ParticipantCrossingPolicyReferenceModel.model_validate(policy) for policy in policies],
        known_evidence_refs=evidence_refs,
        known_authority_basis_refs=KNOWN_AUTHORITY_BASIS_REFS,
    )


def test_crossing_request_is_a_closed_participant_runtime_fact() -> None:
    record = _request()

    assert record.occurrence.stage == "requested"
    assert record.participant_address == "participants.red.operator"
    assert record.occurrence.subject.subject_ref == "control-occurrence.proposal.1"
    assert record.occurrence.policy.policy_decision_ref == "participant-crossing-policy-decision:red:episode-1:8"
    assert record.occurrence.policy.decision_cut_ref == "participant-policy-cut:red:episode-1:8"


def test_crossing_policy_requires_an_exact_policy_decision_identity() -> None:
    policy = _policy()
    del policy["policy_decision_ref"]

    with pytest.raises(ValidationError, match="policy_decision_ref"):
        ParticipantCrossingPolicyReferenceModel.model_validate(policy)


def test_crossing_policy_requires_an_exact_decision_cut() -> None:
    policy = _policy()
    del policy["decision_cut_ref"]

    with pytest.raises(ValidationError, match="decision_cut_ref"):
        ParticipantCrossingPolicyReferenceModel.model_validate(policy)


def test_crossing_request_rejects_payload_policy_and_secret_bags() -> None:
    payload = _envelope(
        {
            "stage": "requested",
            "request_id": "crossing-request.1",
            "requested_operation": "admission",
            "action_or_projection_ref": "action-contract:contain-host",
            "required_evidence_refs": ["evidence-requirement:crossing-decision"],
            "payload": {"prompt": "hidden"},
            "policy": {"body": "permit if secret"},
            "credentials": {"token": "secret"},
        }
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ParticipantCrossingOccurrenceModel.model_validate(payload)


@pytest.mark.parametrize(
    ("stage", "detail"),
    [
        (
            "decided",
            {
                "request_ref": "crossing-request.1",
                "decision_id": "crossing-decision.1",
                "decision_revision": 1,
                "gates": {
                    "caller_authorization": "permit",
                    "target_authorization": "permit",
                    "participant_authority": "permit",
                    "action_admission": "permit",
                    "visibility": "permit",
                    "marking_authorization": "permit",
                    "declassification": "not-applicable",
                    "backend_support": "permit",
                    "transformation_validity": "not-applicable",
                },
                "disposition": "permit",
                "reason_code": "policy-satisfied",
                "required_evidence_refs": ["evidence-requirement:crossing-decision"],
            },
        ),
        (
            "transformed",
            {
                "decision_ref": "crossing-decision.1",
                "transformation_id": "crossing-transformation.1",
                "operation": "redaction",
                "source_subject": _subject(),
                "result_subject": _subject(
                    kind="participant-action-contract",
                    ref="action-contract:redacted-contain-host",
                ),
                "rule_ref": "redaction-rule:participant-output",
                "rule_revision": "2",
                "source_marking_refs": ["marking:participant-control"],
                "result_marking_refs": ["marking:participant-control"],
            },
        ),
        (
            "disclosed",
            {
                "decision_ref": "crossing-decision.1",
                "disclosure_id": "crossing-disclosure.1",
                "operation": "disclosure",
                "source_marking_refs": ["marking:participant-control"],
                "result_marking_refs": ["marking:participant-control"],
            },
        ),
        (
            "delivery-attempted",
            {
                "decision_ref": "crossing-decision.1",
                "attempt_id": "crossing-attempt.1",
                "owning_occurrence_ref": "control-occurrence.proposal.1",
                "disposition": "attempted",
            },
        ),
        (
            "delivered",
            {
                "decision_ref": "crossing-decision.1",
                "attempt_ref": "crossing-attempt.1",
                "delivery_id": "crossing-delivery.1",
                "owning_occurrence_ref": "control-occurrence.proposal.1",
                "delivery_order": 13,
                "disposition": "delivered",
            },
        ),
        (
            "observed",
            {
                "decision_ref": "crossing-decision.1",
                "delivery_ref": "crossing-delivery.1",
                "observation_id": "crossing-observation.1",
                "owning_observation_ref": "observation:red:13",
                "observation_order": 14,
            },
        ),
        (
            "audited",
            {
                "audited_event_ref": "crossing-occurrence.delivered.1",
                "audit_record_ref": "audit:participant-crossing:1",
                "retained_evidence_refs": ["evidence:crossing-1"],
            },
        ),
    ],
)
def test_each_crossing_fact_stage_is_a_distinct_closed_variant(
    stage: str,
    detail: dict[str, object],
) -> None:
    value = _envelope({"stage": stage, **detail})
    if stage == "transformed":
        value["occurrence"]["subject"] = detail["result_subject"]

    parsed = ParticipantCrossingOccurrenceModel.model_validate(value)

    assert parsed.occurrence.stage == stage


def test_deny_first_decision_rejects_permit_when_a_required_gate_denies() -> None:
    request = _request()

    with pytest.raises(ValidationError, match="every applicable gate"):
        _decision(
            request,
            gate_override=("participant_authority", "deny"),
        )


def test_context_validator_accepts_ordered_requested_decided_and_realized_facts() -> None:
    request = _request()
    decision = _decision(request)
    attempt_value = _envelope(
        {
            "stage": "delivery-attempted",
            "decision_ref": "crossing-decision.1",
            "attempt_id": "crossing-attempt.1",
            "owning_occurrence_ref": "control-occurrence.proposal.1",
            "disposition": "attempted",
        }
    )
    attempt_value["event_id"] = "crossing-occurrence.delivery-attempted.1"
    attempt_value["predecessor_event_refs"] = [decision.event_id]
    attempt_value["occurrence"]["effective_order"] = 12
    attempt = ParticipantCrossingOccurrenceModel.model_validate(attempt_value)
    delivery_value = _envelope(
        {
            "stage": "delivered",
            "decision_ref": "crossing-decision.1",
            "attempt_ref": "crossing-attempt.1",
            "delivery_id": "crossing-delivery.1",
            "owning_occurrence_ref": "control-occurrence.proposal.1",
            "delivery_order": 13,
            "disposition": "delivered",
        }
    )
    delivery_value["event_id"] = "crossing-occurrence.delivered.1"
    delivery_value["predecessor_event_refs"] = [attempt.event_id]
    delivery_value["occurrence"]["effective_order"] = 13
    delivery = ParticipantCrossingOccurrenceModel.model_validate(delivery_value)

    validate_participant_crossing_occurrence_context(
        [request, decision, attempt, delivery],
        known_subjects=[ParticipantCrossingSubjectReferenceModel.model_validate(_subject())],
        policies=[ParticipantCrossingPolicyReferenceModel.model_validate(_policy())],
        known_evidence_refs=KNOWN_EVIDENCE_REFS,
        known_authority_basis_refs=KNOWN_AUTHORITY_BASIS_REFS,
    )


def test_context_validator_rejects_unknown_subject_stale_policy_and_missing_evidence() -> None:
    request = _request()
    empty_evidence_refs: set[str] = set()

    with pytest.raises(ValueError, match="typed subject reference must resolve"):
        _validate_context([request], subject_values=[])
    with pytest.raises(ValueError, match="policy revision must resolve"):
        _validate_context([request], policy_values=[])
    with pytest.raises(ValueError, match="evidence reference must resolve"):
        _validate_context([request], known_evidence_refs=empty_evidence_refs)


def test_context_validator_rejects_unresolved_stage_local_evidence() -> None:
    request = _request()

    with pytest.raises(ValueError, match="stage-local evidence reference must resolve"):
        _validate_context([request], known_evidence_refs={"evidence:crossing-1"})


def test_delivery_must_use_the_attempts_exact_decision_and_successful_disposition() -> None:
    request = _request()
    decision = _decision(request)
    second_value = decision.model_dump(mode="json")
    second_value["event_id"] = "crossing-occurrence.decided.2"
    second_value["occurrence"]["decision_id"] = "crossing-decision.2"
    second = ParticipantCrossingOccurrenceModel.model_validate(second_value)
    attempt = _attempt(decision)
    wrong_decision_delivery = _delivery(attempt, decision_ref="crossing-decision.2")

    with pytest.raises(ValueError, match="delivery decision must match its predecessor"):
        _validate_context([request, decision, second, attempt, wrong_decision_delivery])

    failed_attempt = _attempt(decision, disposition="failed")
    delivery_after_failure = _delivery(failed_attempt)
    with pytest.raises(ValueError, match="delivery requires a successful attempt disposition"):
        _validate_context([request, decision, failed_attempt, delivery_after_failure])


def test_delivery_ownership_must_resolve_the_exact_typed_subject() -> None:
    request = _request()
    decision = _decision(request)
    foreign_subject = _subject(
        kind="participant-observation",
        contract_id="participant-observation-envelope-v1",
        ref="observation:foreign",
    )
    attempt = _attempt(decision, owning_occurrence_ref="observation:foreign")
    known_subjects = [_subject(), foreign_subject]

    with pytest.raises(ValueError, match="owner must match its typed subject"):
        _validate_context(
            [request, decision, attempt],
            subject_values=known_subjects,
        )


def test_context_validator_rejects_delivery_without_attempt() -> None:
    request = _request()
    decision = _decision(request)
    delivery_value = _envelope(
        {
            "stage": "delivered",
            "decision_ref": "crossing-decision.1",
            "attempt_ref": "crossing-attempt.missing",
            "delivery_id": "crossing-delivery.1",
            "owning_occurrence_ref": "control-occurrence.proposal.1",
            "delivery_order": 13,
            "disposition": "delivered",
        }
    )
    delivery_value["event_id"] = "crossing-occurrence.delivered.1"
    delivery_value["predecessor_event_refs"] = [decision.event_id]
    delivery_value["occurrence"]["effective_order"] = 13
    delivery = ParticipantCrossingOccurrenceModel.model_validate(delivery_value)

    with pytest.raises(ValueError, match="delivery attempt reference must resolve"):
        _validate_context([request, decision, delivery])


def test_transform_decision_delivers_the_new_subject_after_the_transformation() -> None:
    request = _request()
    decision = _decision(
        request,
        disposition="transform",
        gate_override=("transformation_validity", "permit"),
        required_operation="redaction",
    )
    result_subject = _subject(
        kind="participant-action-contract",
        contract_id="participant-action-contract-v1",
        ref="action-contract:redacted-contain-host",
    )
    transformation_value = _envelope(
        {
            "stage": "transformed",
            "decision_ref": "crossing-decision.1",
            "transformation_id": "crossing-transformation.1",
            "operation": "redaction",
            "source_subject": _subject(),
            "result_subject": result_subject,
            "rule_ref": "redaction-rule:participant-output",
            "rule_revision": "2",
            "source_marking_refs": ["marking:participant-control"],
            "result_marking_refs": ["marking:participant-control"],
        }
    )
    transformation_value["event_id"] = "crossing-occurrence.transformed.1"
    transformation_value["predecessor_event_refs"] = [decision.event_id]
    transformation_value["occurrence"]["effective_order"] = 12
    transformation_value["occurrence"]["subject"] = result_subject
    transformation = ParticipantCrossingOccurrenceModel.model_validate(transformation_value)
    attempt_value = _envelope(
        {
            "stage": "delivery-attempted",
            "decision_ref": "crossing-decision.1",
            "transformation_ref": "crossing-transformation.1",
            "attempt_id": "crossing-attempt.1",
            "owning_occurrence_ref": "action-contract:redacted-contain-host",
            "disposition": "attempted",
        }
    )
    attempt_value["event_id"] = "crossing-occurrence.delivery-attempted.1"
    attempt_value["predecessor_event_refs"] = [transformation.event_id]
    attempt_value["occurrence"]["effective_order"] = 13
    attempt_value["occurrence"]["subject"] = result_subject
    attempt = ParticipantCrossingOccurrenceModel.model_validate(attempt_value)

    validate_participant_crossing_occurrence_context(
        [request, decision, transformation, attempt],
        known_subjects=[
            ParticipantCrossingSubjectReferenceModel.model_validate(_subject()),
            ParticipantCrossingSubjectReferenceModel.model_validate(result_subject),
        ],
        policies=[ParticipantCrossingPolicyReferenceModel.model_validate(_policy())],
        known_evidence_refs=KNOWN_EVIDENCE_REFS,
        known_authority_basis_refs=KNOWN_AUTHORITY_BASIS_REFS,
    )


def test_transform_must_apply_the_exact_operation_prescribed_by_its_decision() -> None:
    request = _request()
    decision = _decision(
        request,
        disposition="transform",
        required_operation="redaction",
    )
    result_subject = _subject(
        kind="participant-action-contract",
        contract_id="participant-action-contract-v1",
        ref="action-contract:masked-contain-host",
    )
    value = _envelope(
        {
            "stage": "transformed",
            "decision_ref": "crossing-decision.1",
            "transformation_id": "crossing-transformation.1",
            "operation": "masking",
            "source_subject": _subject(),
            "result_subject": result_subject,
            "rule_ref": "masking-rule:participant-output",
            "rule_revision": "1",
            "source_marking_refs": ["marking:participant-control"],
            "result_marking_refs": ["marking:participant-control"],
        }
    )
    value["event_id"] = "crossing-occurrence.transformed.1"
    value["predecessor_event_refs"] = [decision.event_id]
    value["occurrence"]["effective_order"] = 12
    value["occurrence"]["subject"] = result_subject
    transformation = ParticipantCrossingOccurrenceModel.model_validate(value)
    known_subjects = [_subject(), result_subject]

    with pytest.raises(ValueError, match="operation must match the decision requirement"):
        _validate_context(
            [request, decision, transformation],
            subject_values=known_subjects,
        )


def test_transformation_rejects_marking_weakening_without_declassification() -> None:
    result_subject = _subject(
        kind="participant-action-contract",
        contract_id="participant-action-contract-v1",
        ref="action-contract:redacted-contain-host",
    )
    value = _envelope(
        {
            "stage": "transformed",
            "decision_ref": "crossing-decision.1",
            "transformation_id": "crossing-transformation.1",
            "operation": "redaction",
            "source_subject": _subject(),
            "result_subject": result_subject,
            "rule_ref": "redaction-rule:participant-output",
            "rule_revision": "2",
            "source_marking_refs": ["marking:restricted"],
            "result_marking_refs": ["marking:public"],
        }
    )
    value["occurrence"]["subject"] = result_subject

    with pytest.raises(ValidationError, match="inherit source markings"):
        ParticipantCrossingOccurrenceModel.model_validate(value)


def test_declassification_basis_is_reserved_for_declassification_operations() -> None:
    result_subject = _subject(
        kind="participant-action-contract",
        contract_id="participant-action-contract-v1",
        ref="action-contract:redacted-contain-host",
    )
    value = _envelope(
        {
            "stage": "transformed",
            "decision_ref": "crossing-decision.1",
            "transformation_id": "crossing-transformation.1",
            "operation": "redaction",
            "source_subject": _subject(),
            "result_subject": result_subject,
            "rule_ref": "redaction-rule:participant-output",
            "rule_revision": "2",
            "source_marking_refs": ["marking:restricted"],
            "result_marking_refs": ["marking:public"],
            "declassification_basis_ref": "authority:untrusted",
        }
    )
    value["occurrence"]["subject"] = result_subject

    with pytest.raises(ValidationError, match="reserved for declassification"):
        ParticipantCrossingOccurrenceModel.model_validate(value)


def test_declassification_basis_must_resolve_as_declared_authority() -> None:
    request = _request()
    decision = _decision(
        request,
        disposition="transform",
        gate_override=("declassification", "permit"),
        required_operation="declassification",
    )
    result_subject = _subject(
        kind="participant-action-contract",
        contract_id="participant-action-contract-v1",
        ref="action-contract:declassified-contain-host",
    )
    value = _envelope(
        {
            "stage": "transformed",
            "decision_ref": "crossing-decision.1",
            "transformation_id": "crossing-transformation.1",
            "operation": "declassification",
            "source_subject": _subject(),
            "result_subject": result_subject,
            "rule_ref": "declassification-rule:participant-output",
            "rule_revision": "1",
            "source_marking_refs": ["marking:restricted"],
            "result_marking_refs": ["marking:public"],
            "declassification_basis_ref": "authority:untrusted",
        }
    )
    value["event_id"] = "crossing-occurrence.transformed.1"
    value["predecessor_event_refs"] = [decision.event_id]
    value["occurrence"]["effective_order"] = 12
    value["occurrence"]["subject"] = result_subject
    transformation = ParticipantCrossingOccurrenceModel.model_validate(value)
    known_subjects = [_subject(), result_subject]

    with pytest.raises(ValueError, match="declassification authority basis must resolve"):
        _validate_context(
            [request, decision, transformation],
            subject_values=known_subjects,
        )


def test_crossing_rejects_a_policy_revision_that_becomes_effective_later() -> None:
    value = _envelope(
        {
            "stage": "requested",
            "request_id": "crossing-request.1",
            "requested_operation": "admission",
            "action_or_projection_ref": "action-contract:contain-host",
            "required_evidence_refs": ["evidence-requirement:crossing-decision"],
        }
    )
    value["occurrence"]["policy"]["effective_order"] = 12

    with pytest.raises(ValidationError, match="future policy revision"):
        ParticipantCrossingOccurrenceModel.model_validate(value)


def test_observation_and_audit_require_their_own_ordered_occurrence_facts() -> None:
    request = _request()
    decision = _decision(request)
    attempt_value = _envelope(
        {
            "stage": "delivery-attempted",
            "decision_ref": "crossing-decision.1",
            "attempt_id": "crossing-attempt.1",
            "owning_occurrence_ref": "control-occurrence.proposal.1",
            "disposition": "attempted",
        }
    )
    attempt_value["event_id"] = "crossing-occurrence.delivery-attempted.1"
    attempt_value["predecessor_event_refs"] = [decision.event_id]
    attempt_value["occurrence"]["effective_order"] = 12
    attempt = ParticipantCrossingOccurrenceModel.model_validate(attempt_value)
    delivery_value = _envelope(
        {
            "stage": "delivered",
            "decision_ref": "crossing-decision.1",
            "attempt_ref": "crossing-attempt.1",
            "delivery_id": "crossing-delivery.1",
            "owning_occurrence_ref": "control-occurrence.proposal.1",
            "delivery_order": 13,
            "disposition": "delivered",
        }
    )
    delivery_value["event_id"] = "crossing-occurrence.delivered.1"
    delivery_value["predecessor_event_refs"] = [attempt.event_id]
    delivery_value["occurrence"]["effective_order"] = 13
    delivery = ParticipantCrossingOccurrenceModel.model_validate(delivery_value)
    observation_subject = _subject(
        kind="participant-observation",
        contract_id="participant-observation-envelope-v1",
        ref="observation:red:13",
    )
    observation_value = _envelope(
        {
            "stage": "observed",
            "decision_ref": "crossing-decision.1",
            "delivery_ref": "crossing-delivery.1",
            "observation_id": "crossing-observation.1",
            "owning_observation_ref": "observation:red:13",
            "observation_order": 14,
        }
    )
    observation_value["event_id"] = "crossing-occurrence.observed.1"
    observation_value["predecessor_event_refs"] = [delivery.event_id]
    observation_value["occurrence"]["effective_order"] = 14
    observation_value["occurrence"]["subject"] = observation_subject
    observation = ParticipantCrossingOccurrenceModel.model_validate(observation_value)
    audit_value = _envelope(
        {
            "stage": "audited",
            "audited_event_ref": observation.event_id,
            "audit_record_ref": "audit:participant-crossing:1",
            "retained_evidence_refs": ["evidence:crossing-1"],
        }
    )
    audit_value["event_id"] = "crossing-occurrence.audited.1"
    audit_value["predecessor_event_refs"] = [observation.event_id]
    audit_value["occurrence"]["effective_order"] = 15
    audit_value["occurrence"]["subject"] = observation_subject
    audit = ParticipantCrossingOccurrenceModel.model_validate(audit_value)

    validate_participant_crossing_occurrence_context(
        [request, decision, attempt, delivery, observation, audit],
        known_subjects=[
            ParticipantCrossingSubjectReferenceModel.model_validate(_subject()),
            ParticipantCrossingSubjectReferenceModel.model_validate(observation_subject),
        ],
        policies=[ParticipantCrossingPolicyReferenceModel.model_validate(_policy())],
        known_evidence_refs=KNOWN_EVIDENCE_REFS,
        known_authority_basis_refs=KNOWN_AUTHORITY_BASIS_REFS,
    )


def test_context_validator_rejects_a_transformation_cycle() -> None:
    request_a = _request()
    decision_a = _decision(
        request_a,
        disposition="transform",
        gate_override=("transformation_validity", "permit"),
        required_operation="redaction",
    )
    subject_a = _subject()
    subject_b = _subject(
        kind="participant-action-contract",
        contract_id="participant-action-contract-v1",
        ref="action-contract:redacted-contain-host",
    )
    transform_a_value = _envelope(
        {
            "stage": "transformed",
            "decision_ref": "crossing-decision.1",
            "transformation_id": "crossing-transformation.1",
            "operation": "redaction",
            "source_subject": subject_a,
            "result_subject": subject_b,
            "rule_ref": "redaction-rule:a-to-b",
            "rule_revision": "1",
            "source_marking_refs": ["marking:participant-control"],
            "result_marking_refs": ["marking:participant-control"],
        }
    )
    transform_a_value["event_id"] = "crossing-occurrence.transformed.1"
    transform_a_value["predecessor_event_refs"] = [decision_a.event_id]
    transform_a_value["occurrence"]["effective_order"] = 12
    transform_a_value["occurrence"]["subject"] = subject_b
    transform_a = ParticipantCrossingOccurrenceModel.model_validate(transform_a_value)
    request_b_value = _envelope(
        {
            "stage": "requested",
            "request_id": "crossing-request.2",
            "requested_operation": "admission",
            "action_or_projection_ref": "action-contract:redacted-contain-host",
            "required_evidence_refs": ["evidence-requirement:crossing-decision"],
        }
    )
    request_b_value["event_id"] = "crossing-occurrence.requested.2"
    request_b_value["occurrence"]["effective_order"] = 13
    request_b_value["occurrence"]["subject"] = subject_b
    request_b = ParticipantCrossingOccurrenceModel.model_validate(request_b_value)
    decision_b_value = _envelope(
        {
            "stage": "decided",
            "request_ref": "crossing-request.2",
            "decision_id": "crossing-decision.2",
            "decision_revision": 1,
            "gates": decision_a.occurrence.gates.model_dump(mode="json"),
            "disposition": "transform",
            "reason_code": "transformation-required",
            "required_operation": "redaction",
            "required_evidence_refs": ["evidence-requirement:crossing-decision"],
        }
    )
    decision_b_value["event_id"] = "crossing-occurrence.decided.2"
    decision_b_value["predecessor_event_refs"] = [request_b.event_id]
    decision_b_value["occurrence"]["effective_order"] = 14
    decision_b_value["occurrence"]["subject"] = subject_b
    decision_b = ParticipantCrossingOccurrenceModel.model_validate(decision_b_value)
    transform_b_value = _envelope(
        {
            "stage": "transformed",
            "decision_ref": "crossing-decision.2",
            "transformation_id": "crossing-transformation.2",
            "operation": "redaction",
            "source_subject": subject_b,
            "result_subject": subject_a,
            "rule_ref": "redaction-rule:b-to-a",
            "rule_revision": "1",
            "source_marking_refs": ["marking:participant-control"],
            "result_marking_refs": ["marking:participant-control"],
        }
    )
    transform_b_value["event_id"] = "crossing-occurrence.transformed.2"
    transform_b_value["predecessor_event_refs"] = [decision_b.event_id]
    transform_b_value["occurrence"]["effective_order"] = 15
    transform_b = ParticipantCrossingOccurrenceModel.model_validate(transform_b_value)

    with pytest.raises(ValueError, match="transformation cycle"):
        _validate_context(
            [request_a, decision_a, transform_a, request_b, decision_b, transform_b],
            subject_values=[subject_a, subject_b],
        )


def test_published_schema_fixtures_bundle_and_consumer_match_the_model() -> None:
    schema = schema_bundle()[CONTRACT_ID]
    published_path = REPO_ROOT / "contracts" / "schemas" / "participant-runtime" / f"{CONTRACT_ID}.json"
    published = json.loads(published_path.read_text(encoding="utf-8"))
    assert published == schema
    assert schema["additionalProperties"] is False
    assert schema["x-raes-invariants"]

    fixture_root = REPO_ROOT / "contracts" / "fixtures" / "participant-runtime" / CONTRACT_ID
    valid_paths = sorted((fixture_root / "valid").glob("*.json"))
    invalid_paths = sorted((fixture_root / "invalid").glob("*.json"))
    assert valid_paths
    assert invalid_paths
    validator = Draft202012Validator(schema)
    for path in valid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(payload)
        parsed = ParticipantCrossingOccurrenceModel.model_validate(payload)
        assert ParticipantCrossingOccurrenceModel.model_validate_json(parsed.model_dump_json()) == parsed
        assert not validate_contract_payload(CONTRACT_ID, payload)
    for path in invalid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(payload))
        with pytest.raises(ValidationError):
            ParticipantCrossingOccurrenceModel.model_validate(payload)


def test_crossing_closed_vocabularies_have_one_concept_authority() -> None:
    catalog = load_controlled_vocabulary_catalog()
    expected = {
        "participant-crossing-directions": {value.value for value in ParticipantCrossingDirection},
        "participant-crossing-interaction-kinds": {value.value for value in ParticipantCrossingInteractionKind},
        "participant-crossing-subject-kinds": {value.value for value in ParticipantCrossingSubjectKind},
        "participant-crossing-operations": {value.value for value in ParticipantCrossingOperation},
        "participant-crossing-gate-dispositions": {value.value for value in ParticipantCrossingGateDisposition},
        "participant-crossing-decision-dispositions": {value.value for value in ParticipantCrossingDecisionDisposition},
        "participant-crossing-backend-postures": {value.value for value in ParticipantCrossingBackendPosture},
        "participant-crossing-loss-kinds": {value.value for value in ParticipantCrossingLossKind},
        "participant-crossing-stages": {
            "requested",
            "decided",
            "transformed",
            "disclosed",
            "delivery-attempted",
            "delivered",
            "observed",
            "audited",
        },
    }

    for vocabulary_id, terms in expected.items():
        vocabulary = catalog.vocabularies[vocabulary_id]
        assert vocabulary.extension_policy == "closed"
        assert set(vocabulary.terms) == terms

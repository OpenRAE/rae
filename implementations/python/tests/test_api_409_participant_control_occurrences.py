"""API-409 participant external-input and intervention contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.contracts import (
    ParticipantControlDeclarationModel,
    ParticipantControlOccurrenceModel,
    validate_participant_control_occurrence_context,
)
from raes_contracts.contracts.participant_control import ParticipantControlTargetContextModel
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ID = "participant-control-occurrence-v1"


def _envelope(occurrence: dict[str, object]) -> dict[str, object]:
    return {
        "event_id": f"control-occurrence.{occurrence['kind']}.1",
        "schema_name": "participant-control-occurrence",
        "schema_version": "1.0.0",
        "event_type": "participant-control-occurrence",
        "extension_policy": "closed",
        "participant_address": "participants.red.operator",
        "episode_id": "episode-1",
        "occurred_at": "2026-07-24T08:00:00Z",
        "recorded_at": "2026-07-24T08:00:01Z",
        "ingested_at": "2026-07-24T08:00:02Z",
        "clock_authority": "clock.logical",
        "ordering_basis": "logical_clock",
        "logical_order_ref": "order:10",
        "actor_ref": "controller.human.red",
        "producer_ref": "participant-runtime.red",
        "provenance_refs": ["provenance:control-1"],
        "evidence_refs": ["evidence:control-1"],
        "object_marking_refs": ["marking:participant-control"],
        "authorization_scope": "scope:red-team",
        "occurrence": {
            "declaration_ref": f"control-transition.{occurrence['kind']}",
            "controller_ref": "controller.human.red",
            "controller_state_ref": "controller-state.human",
            "authority_basis_refs": ["authority:red-team"],
            "controlled_scope_refs": ["scope:red-team"],
            "behavior_specification_ref": "behavior-spec:red",
            "mixed_control_policy_ref": "mixed-control:red",
            "policy_revision": "policy-v3",
            "expected_state_revision": 4,
            "effective_order": 10,
            "valid_from_order": 8,
            "valid_until_order": 12,
            "disposition": "recorded",
            "occurrence_revision": 1,
            "limitation_refs": ["limitation:not-admitted"],
            **occurrence,
        },
    }


def test_proposal_occurrence_is_a_closed_participant_runtime_fact() -> None:
    occurrence = ParticipantControlOccurrenceModel.model_validate(
        _envelope(
            {
                "kind": "proposal",
                "proposal_id": "proposal.1",
                "proposal_revision": 1,
                "admission_status": "not-admitted",
                "action_contract_ref": "action-contract:contain-host",
                "decision_surface_ref": "decision-surface:red:10",
                "payload_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            }
        )
    )

    assert occurrence.occurrence.kind.value == "proposal"
    assert occurrence.participant_address == "participants.red.operator"


@pytest.mark.parametrize(
    "detail",
    [
        {
            "kind": "approval",
            "proposal_ref": "proposal.1",
            "proposal_revision": 1,
            "decision_ref": "decision.approval.1",
            "decision_revision": 1,
        },
        {
            "kind": "denial",
            "proposal_ref": "proposal.1",
            "proposal_revision": 1,
            "decision_ref": "decision.denial.1",
            "decision_revision": 1,
        },
        {
            "kind": "external-direction",
            "target_kind": "action",
            "target_ref": "action:contain-host",
            "target_revision": 2,
        },
        {
            "kind": "intervention",
            "affected_occurrence_ref": "attempt:contain-host:1",
            "affected_target_kind": "attempt",
            "affected_revision": 1,
            "intervention_ref": "intervention:pause",
        },
        {
            "kind": "handoff",
            "prior_controller_state_ref": "controller-state.human",
            "resulting_controller_state_ref": "controller-state.automation",
            "resulting_state_revision": 5,
            "completion_evidence_ref": "evidence:handoff-complete",
        },
        {
            "kind": "override",
            "superseded_occurrence_ref": "decision.approval.1",
            "superseded_target_kind": "decision",
            "superseded_revision": 1,
            "replacement_ref": "decision.override.1",
        },
        {
            "kind": "cancellation",
            "target_kind": "attempt",
            "target_ref": "attempt:contain-host:1",
            "target_revision": 1,
            "cancellation_effect": "partial-limitation",
        },
    ],
)
def test_each_control_fact_kind_has_a_closed_variant(detail: dict[str, object]) -> None:
    parsed = ParticipantControlOccurrenceModel.model_validate(_envelope(detail))

    assert parsed.occurrence.kind.value == detail["kind"]


def test_control_occurrence_rejects_hidden_payload_and_free_form_details() -> None:
    value = _envelope(
        {
            "kind": "approval",
            "proposal_ref": "proposal.1",
            "proposal_revision": 1,
            "decision_ref": "decision.approval.1",
            "decision_revision": 1,
            "details": {"raw_rejected_input": "secret"},
        }
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ParticipantControlOccurrenceModel.model_validate(value)


def _declaration(kind: str, *, order: int = 10) -> ParticipantControlDeclarationModel:
    return ParticipantControlDeclarationModel.model_validate(
        {
            "declaration_ref": f"control-transition.{kind}",
            "kind": kind,
            "participant_address": "participants.red.operator",
            "episode_id": "episode-1",
            "controller_ref": "controller.human.red",
            "controller_state_ref": "controller-state.human",
            "authority_basis_refs": ["authority:red-team"],
            "controlled_scope_refs": ["scope:red-team"],
            "behavior_specification_ref": "behavior-spec:red",
            "mixed_control_policy_ref": "mixed-control:red",
            "policy_revision": "policy-v3",
            "expected_state_revision": 4,
            "effective_order": order,
            "valid_from_order": 8,
            "valid_until_order": 12,
        }
    )


def _proposal_and_approval() -> tuple[ParticipantControlOccurrenceModel, ParticipantControlOccurrenceModel]:
    proposal = ParticipantControlOccurrenceModel.model_validate(
        _envelope(
            {
                "kind": "proposal",
                "proposal_id": "proposal.1",
                "proposal_revision": 1,
                "admission_status": "not-admitted",
                "action_contract_ref": "action-contract:contain-host",
                "payload_ref": "payload:proposal.1",
            }
        )
    )
    approval_value = _envelope(
        {
            "kind": "approval",
            "proposal_ref": "proposal.1",
            "proposal_revision": 1,
            "decision_ref": "decision.approval.1",
            "decision_revision": 1,
        }
    )
    approval_value["event_id"] = "control-occurrence.approval.1"
    approval_value["logical_order_ref"] = "order:11"
    approval_value["predecessor_event_refs"] = [proposal.event_id]
    approval_value["occurrence"]["effective_order"] = 11
    approval = ParticipantControlOccurrenceModel.model_validate(approval_value)
    return proposal, approval


def _transformed_proposal() -> tuple[ParticipantControlOccurrenceModel, ParticipantControlOccurrenceModel]:
    source, _ = _proposal_and_approval()
    transformed_value = _envelope(
        {
            "kind": "proposal",
            "proposal_id": "proposal.2",
            "proposal_revision": 1,
            "admission_status": "not-admitted",
            "action_contract_ref": "action-contract:contain-host",
            "payload_ref": "payload:proposal.2",
            "source_proposal_ref": "proposal.1",
            "source_proposal_revision": 1,
            "transformation_ref": "transformation:redaction.1",
        }
    )
    transformed_value["event_id"] = "control-occurrence.proposal.2"
    transformed_value["provenance_refs"] = [
        "provenance:transformation.1",
        source.event_id,
        "transformation:redaction.1",
    ]
    return source, ParticipantControlOccurrenceModel.model_validate(transformed_value)


def test_cross_record_validator_accepts_revisioned_proposal_decision_chain_and_replay() -> None:
    proposal, approval = _proposal_and_approval()

    validate_participant_control_occurrence_context(
        [proposal, approval, proposal, approval],
        declarations=[_declaration("proposal"), _declaration("approval", order=11)],
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unknown-declaration", "declaration reference must resolve"),
        ("authority-confusion", "declaration coordinates disagree"),
        ("stale-policy", "declaration coordinates disagree"),
        ("unknown-proposal", "proposal reference must resolve"),
        ("stale-proposal", "proposal revision is stale"),
        ("missing-predecessor", "decision must follow its proposal occurrence"),
        ("identity-reuse", "event identity was reused with different semantics"),
    ],
)
def test_cross_record_validator_fails_closed_on_reference_and_identity_errors(
    mutation: str,
    message: str,
) -> None:
    proposal, approval = _proposal_and_approval()
    records = [proposal, approval]
    declarations = [_declaration("proposal"), _declaration("approval", order=11)]

    if mutation == "unknown-declaration":
        approval.occurrence.declaration_ref = "control-transition.unknown"
    elif mutation == "authority-confusion":
        approval.occurrence.controller_ref = "controller.automation.red"
    elif mutation == "stale-policy":
        approval.occurrence.policy_revision = "policy-v2"
    elif mutation == "unknown-proposal":
        approval.occurrence.proposal_ref = "proposal.unknown"
    elif mutation == "stale-proposal":
        approval.occurrence.proposal_revision = 2
    elif mutation == "missing-predecessor":
        approval.predecessor_event_refs = []
    else:
        conflicting = proposal.model_copy(deep=True)
        conflicting.occurrence.payload_ref = "payload:proposal.changed"
        records.append(conflicting)

    with pytest.raises(ValueError, match=message):
        validate_participant_control_occurrence_context(records, declarations=declarations)


@pytest.mark.parametrize(
    ("identity_kind", "message"),
    [
        ("declaration", "declaration identity was reused with different semantics"),
        ("proposal", "proposal identity was reused with different semantics"),
        ("decision", "decision identity was reused"),
        ("target", "target identity was reused with different revision or scope"),
    ],
)
def test_cross_record_validator_rejects_semantic_identity_reuse(identity_kind: str, message: str) -> None:
    proposal, approval = _proposal_and_approval()
    records: list[ParticipantControlOccurrenceModel] = []
    declarations = [_declaration("proposal")]
    known_targets: list[ParticipantControlTargetContextModel] = []

    if identity_kind == "declaration":
        conflicting = _declaration("proposal").model_copy(update={"policy_revision": "policy-v4"})
        declarations.append(conflicting)
    elif identity_kind == "proposal":
        conflicting = proposal.model_copy(deep=True)
        conflicting.event_id = "control-occurrence.proposal.2"
        conflicting.occurrence.payload_ref = "payload:proposal.changed"
        records = [proposal, conflicting]
    elif identity_kind == "decision":
        conflicting = approval.model_copy(deep=True)
        conflicting.event_id = "control-occurrence.approval.2"
        records = [proposal, approval, conflicting]
    else:
        target = ParticipantControlTargetContextModel(
            target_kind="action",
            target_ref="action:contain-host",
            target_revision=1,
            participant_address="participants.red.operator",
            episode_id="episode-1",
        )
        known_targets = [target, target.model_copy(update={"target_revision": 2})]

    with pytest.raises(ValueError, match=message):
        validate_participant_control_occurrence_context(
            records,
            declarations=declarations,
            known_targets=known_targets,
        )


def test_typed_target_context_enforces_kind_revision_and_scope_for_external_relations() -> None:
    direction = ParticipantControlOccurrenceModel.model_validate(
        _envelope(
            {
                "kind": "external-direction",
                "target_kind": "action",
                "target_ref": "action:contain-host",
                "target_revision": 2,
            }
        )
    )
    declaration = _declaration("external-direction")
    target = ParticipantControlTargetContextModel(
        target_kind="action",
        target_ref="action:contain-host",
        target_revision=2,
        participant_address=direction.participant_address,
        episode_id=direction.episode_id,
    )

    validate_participant_control_occurrence_context(
        [direction],
        declarations=[declaration],
        known_targets=[target],
    )

    stale_target = target.model_copy(update={"target_revision": 1})
    with pytest.raises(ValueError, match="target revision must match"):
        validate_participant_control_occurrence_context(
            [direction],
            declarations=[declaration],
            known_targets=[stale_target],
        )
    other_scope_target = target.model_copy(update={"episode_id": "episode-other"})
    with pytest.raises(ValueError, match="target scope must match"):
        validate_participant_control_occurrence_context(
            [direction],
            declarations=[declaration],
            known_targets=[other_scope_target],
        )


def test_typed_target_context_rejects_an_unknown_kind_and_reference_pair() -> None:
    direction = ParticipantControlOccurrenceModel.model_validate(
        _envelope(
            {
                "kind": "external-direction",
                "target_kind": "action",
                "target_ref": "action:unknown",
                "target_revision": 1,
            }
        )
    )
    declaration = _declaration("external-direction")

    with pytest.raises(ValueError, match="typed target reference and kind must resolve"):
        validate_participant_control_occurrence_context(
            [direction],
            declarations=[declaration],
        )


def test_rejected_typed_target_preserves_the_invalid_attempt_without_becoming_a_target() -> None:
    value = _envelope(
        {
            "kind": "external-direction",
            "target_kind": "action",
            "target_ref": "action:unknown",
            "target_revision": 1,
        }
    )
    value["occurrence"]["disposition"] = "rejected"
    value["occurrence"]["reason_code"] = "invalid-target"
    direction = ParticipantControlOccurrenceModel.model_validate(value)

    validate_participant_control_occurrence_context(
        [direction],
        declarations=[_declaration("external-direction")],
    )
    intervention = ParticipantControlOccurrenceModel.model_validate(
        _envelope(
            {
                "kind": "intervention",
                "affected_target_kind": "control",
                "affected_occurrence_ref": direction.event_id,
                "affected_revision": direction.occurrence.occurrence_revision,
                "intervention_ref": "intervention:rejected-direction",
            }
        )
    )

    records = [direction, intervention]
    declarations = [
        _declaration("external-direction"),
        _declaration("intervention"),
    ]
    with pytest.raises(ValueError, match="typed target reference and kind must resolve"):
        validate_participant_control_occurrence_context(
            records,
            declarations=declarations,
        )


def test_transformed_proposal_requires_source_provenance_and_marking_inheritance() -> None:
    source, transformed = _transformed_proposal()
    assert transformed.occurrence.admission_status == "not-admitted"

    transformed.provenance_refs = ["provenance:transformation.1"]
    declaration = _declaration("proposal")
    with pytest.raises(ValueError, match="transformed proposal provenance must bind its source and transformation"):
        validate_participant_control_occurrence_context(
            [source, transformed],
            declarations=[declaration],
        )

    transformed.provenance_refs.extend([source.event_id, "transformation:redaction.1"])
    validate_participant_control_occurrence_context(
        [source, transformed],
        declarations=[declaration],
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unknown-source", "transformed proposal source must resolve"),
        ("stale-source", "transformed proposal source revision is stale"),
        ("source-scope", "transformed proposal scope must match its source"),
        ("source-marking", "transformed proposal must inherit source markings"),
    ],
)
def test_transformed_proposal_fails_closed_on_source_join_errors(mutation: str, message: str) -> None:
    source, transformed = _transformed_proposal()
    declarations = [_declaration("proposal")]

    if mutation == "unknown-source":
        transformed.occurrence.source_proposal_ref = "proposal.unknown"
    elif mutation == "stale-source":
        transformed.occurrence.source_proposal_revision = 2
    elif mutation == "source-scope":
        transformed.episode_id = "episode-other"
        transformed.occurrence.declaration_ref = "control-transition.proposal-other"
        declarations.append(
            _declaration("proposal").model_copy(
                update={"declaration_ref": "control-transition.proposal-other", "episode_id": "episode-other"}
            )
        )
    else:
        source.object_marking_refs.append("marking:source-only")

    with pytest.raises(ValueError, match=message):
        validate_participant_control_occurrence_context(
            [source, transformed],
            declarations=declarations,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("scope", "decision scope must match its proposal"),
        ("order", "decision order must follow its proposal"),
    ],
)
def test_proposal_decision_fails_closed_on_scope_and_order_errors(mutation: str, message: str) -> None:
    proposal, approval = _proposal_and_approval()
    declarations = [_declaration("proposal"), _declaration("approval", order=11)]

    if mutation == "scope":
        approval.episode_id = "episode-other"
        approval.occurrence.declaration_ref = "control-transition.approval-other"
        declarations[1] = declarations[1].model_copy(
            update={"declaration_ref": "control-transition.approval-other", "episode_id": "episode-other"}
        )
    else:
        approval.occurrence.effective_order = 10
        declarations[1] = _declaration("approval", order=10)

    with pytest.raises(ValueError, match=message):
        validate_participant_control_occurrence_context(
            [proposal, approval],
            declarations=declarations,
        )


def test_handoff_rejects_a_prior_controller_state_that_disagrees_with_the_occurrence() -> None:
    handoff = ParticipantControlOccurrenceModel.model_validate(
        _envelope(
            {
                "kind": "handoff",
                "prior_controller_state_ref": "controller-state.other",
                "resulting_controller_state_ref": "controller-state.automation",
                "resulting_state_revision": 5,
                "completion_evidence_ref": "evidence:handoff-complete",
            }
        )
    )
    declaration = _declaration("handoff")

    with pytest.raises(ValueError, match="handoff prior controller state must match"):
        validate_participant_control_occurrence_context(
            [handoff],
            declarations=[declaration],
        )


def test_published_schema_and_fixtures_match_the_closed_reference_model() -> None:
    schema = schema_bundle()[CONTRACT_ID]
    published = json.loads(
        (REPO_ROOT / "contracts" / "schemas" / "participant-runtime" / f"{CONTRACT_ID}.json").read_text(
            encoding="utf-8"
        )
    )
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
        value = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(value)
        ParticipantControlOccurrenceModel.model_validate(value)
    for path in invalid_paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(value))
        with pytest.raises(ValidationError):
            ParticipantControlOccurrenceModel.model_validate(value)

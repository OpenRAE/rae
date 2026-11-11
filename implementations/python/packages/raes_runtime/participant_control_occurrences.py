"""API-409 occurrence construction for RUN-310 runtime mediation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from pydantic import ValidationError
from raes_contracts.contracts import ParticipantControlOccurrenceModel
from raes_contracts.contracts.participant_control import ParticipantCancellationEffect
from raes_contracts.errors import InvalidInputError
from raes_contracts.participant_mixed_control_vocabulary import ParticipantControlTargetKind
from raes_contracts.timestamps import isoformat_z
from raes_processor.models import (
    MixedControlControllerStateRuntime,
    MixedControlTransitionRuntime,
    ParticipantBehaviorSpecificationRuntime,
)

from .participant_control_intents import (
    ParticipantApprovalControlIntent,
    ParticipantCancellationControlIntent,
    ParticipantControlIntent,
    ParticipantDenialControlIntent,
    ParticipantExternalDirectionControlIntent,
    ParticipantHandoffControlIntent,
    ParticipantInterventionControlIntent,
    ParticipantOverrideControlIntent,
    ParticipantProposalControlIntent,
)
from .participant_control_targets import ResolvedParticipantControlTarget


@dataclass(frozen=True)
class ParticipantControlOccurrenceContext:
    """Trusted runtime-owned inputs used to construct one occurrence."""

    control_plane: object
    participant_address: str
    specification: ParticipantBehaviorSpecificationRuntime
    transition: MixedControlTransitionRuntime
    state: MixedControlControllerStateRuntime
    history: list[dict[str, object]]


def build_participant_control_occurrence(
    context: ParticipantControlOccurrenceContext,
    intent: ParticipantControlIntent,
    *,
    resolved_target: ResolvedParticipantControlTarget | None,
    accepted: bool,
    rejection_reason: str | None,
) -> ParticipantControlOccurrenceModel:
    """Build one immutable runtime-owned occurrence from a caller intent."""

    control_plane = context.control_plane
    participant_address = context.participant_address
    specification = context.specification
    transition = context.transition
    state = context.state
    history = context.history
    now = isoformat_z(control_plane.wall_clock())
    detail: dict[str, object] = {
        "kind": intent.kind,
        "declaration_ref": transition.address,
        "controller_ref": state.controller_address,
        "controller_state_ref": state.address,
        "authority_basis_refs": list(state.authority_basis_addresses or state.authority_basis_refs),
        "controlled_scope_refs": list(state.scope_addresses or state.scope_refs),
        "behavior_specification_ref": specification.address,
        "mixed_control_policy_ref": specification.address,
        "policy_revision": transition.policy_revision,
        "expected_state_revision": transition.expected_state_revision,
        "effective_order": transition.effective_order,
        "valid_from_order": transition.valid_from_order,
        "valid_until_order": transition.valid_until_order,
        "occurrence_revision": len(history) + 1,
        "disposition": "accepted" if accepted else "rejected",
        "reason_code": rejection_reason,
        "limitation_refs": list(intent.limitation_refs),
        **_kind_detail(intent, transition),
    }
    payload = {
        "event_id": f"participant-control.{uuid4()}",
        "schema_name": "participant-control-occurrence",
        "schema_version": "1.0.0",
        "event_type": "participant-control-occurrence",
        "extension_policy": "closed",
        "participant_address": participant_address,
        "episode_id": intent.episode_id,
        "occurred_at": now,
        "recorded_at": now,
        "ingested_at": now,
        "clock_authority": "runtime.control-plane.clock",
        "ordering_basis": "logical_clock",
        "logical_order_ref": f"effective-order:{transition.effective_order}",
        "predecessor_event_refs": [resolved_target.predecessor_ref] if resolved_target is not None else [],
        "actor_ref": state.controller_address,
        "producer_ref": f"runtime.control-plane.{control_plane.target_name}",
        "provenance_refs": list(intent.provenance_refs),
        "evidence_refs": list(intent.evidence_refs),
        "object_marking_refs": list(intent.object_marking_refs),
        "authorization_scope": (state.scope_addresses or state.scope_refs)[0],
        "occurrence": detail,
    }
    try:
        return ParticipantControlOccurrenceModel.model_validate(payload)
    # The intent model admits values, such as an empty reference, that the occurrence contract refuses.
    except ValidationError as exc:
        raise InvalidInputError("participant control intent does not form a valid control occurrence") from exc


def _kind_detail(
    intent: ParticipantControlIntent,
    transition: MixedControlTransitionRuntime,
) -> dict[str, object]:
    if isinstance(intent, ParticipantProposalControlIntent):
        detail = {
            "proposal_id": intent.proposal_id,
            "proposal_revision": intent.proposal_revision,
            "admission_status": "not-admitted",
            "action_contract_ref": intent.action_contract_ref,
            "decision_surface_ref": intent.decision_surface_ref,
            "proposal_binding_ref": intent.proposal_binding_ref,
            "payload_ref": intent.payload_ref,
            "payload_digest": intent.payload_digest,
            "source_proposal_ref": intent.source_proposal_ref,
            "source_proposal_revision": intent.source_proposal_revision,
            "transformation_ref": intent.transformation_ref,
        }
    elif isinstance(intent, (ParticipantApprovalControlIntent, ParticipantDenialControlIntent)):
        detail = {
            "proposal_ref": intent.proposal_ref,
            "proposal_revision": intent.proposal_revision,
            "decision_ref": intent.decision_ref,
            "decision_revision": intent.decision_revision,
        }
    elif isinstance(intent, ParticipantExternalDirectionControlIntent):
        detail = {
            "target_kind": intent.target_kind.value,
            "target_ref": intent.target_ref,
            "target_revision": intent.target_revision,
        }
    elif isinstance(intent, ParticipantInterventionControlIntent):
        detail = {
            "affected_target_kind": intent.affected_target_kind.value,
            "affected_occurrence_ref": intent.affected_occurrence_ref,
            "affected_revision": intent.affected_revision,
            "intervention_ref": intent.intervention_ref,
        }
    elif isinstance(intent, ParticipantHandoffControlIntent):
        detail = {
            "prior_controller_state_ref": transition.from_state_address,
            "resulting_controller_state_ref": transition.to_state_address,
            "resulting_state_revision": transition.resulting_state_revision,
            "completion_evidence_ref": intent.completion_evidence_ref,
        }
    elif isinstance(intent, ParticipantOverrideControlIntent):
        detail = {
            "superseded_target_kind": intent.superseded_target_kind.value,
            "superseded_occurrence_ref": intent.superseded_occurrence_ref,
            "superseded_revision": intent.superseded_revision,
            "replacement_ref": intent.replacement_ref,
        }
    else:
        assert isinstance(intent, ParticipantCancellationControlIntent)
        detail = {
            "target_kind": intent.target_kind.value,
            "target_ref": intent.target_ref,
            "target_revision": intent.target_revision,
            "cancellation_effect": _cancellation_effect(intent.target_kind).value,
        }
    return detail


def _cancellation_effect(target_kind: ParticipantControlTargetKind) -> ParticipantCancellationEffect:
    if target_kind in {ParticipantControlTargetKind.PROPOSAL, ParticipantControlTargetKind.DECISION}:
        return ParticipantCancellationEffect.PREVENTED
    if target_kind is ParticipantControlTargetKind.ADMITTED_ACTION:
        return ParticipantCancellationEffect.PARTIAL_LIMITATION
    return ParticipantCancellationEffect.TOO_LATE


__all__ = (
    "ParticipantControlOccurrenceContext",
    "build_participant_control_occurrence",
)

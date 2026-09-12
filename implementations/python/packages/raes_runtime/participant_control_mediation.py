"""RUN-310 live supervisory mediation over compiled ACT-617 policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace

from raes_contracts.contracts import (
    ParticipantControlDeclarationModel,
    ParticipantControlOccurrenceModel,
    validate_participant_control_occurrence_context,
)
from raes_contracts.contracts.participant_control import (
    ParticipantControlDisposition,
    ParticipantControlTargetContextModel,
)
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    RuntimeSnapshot,
)
from raes_processor.models import (
    MixedControlControllerStateRuntime,
    MixedControlTransitionRuntime,
    ParticipantBehaviorSpecificationRuntime,
)

from .control_plane_mutation import control_plane_mutation
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .participant_control_intents import ParticipantControlIntent
from .participant_control_occurrences import (
    ParticipantControlOccurrenceContext,
    build_participant_control_occurrence,
)
from .participant_control_operation import (
    ParticipantControlOperationAuthority,
    participant_control_operation_artifacts,
)
from .participant_control_rejections import participant_control_rejection_reason
from .participant_control_targets import (
    participant_control_target_contexts,
    resolve_participant_control_target,
)


@dataclass(frozen=True)
class _BoundControlRequest:
    specification: ParticipantBehaviorSpecificationRuntime
    transition: MixedControlTransitionRuntime
    state: MixedControlControllerStateRuntime
    semantic_fingerprint: str
    scoped_key: str
    context: OperationAdmissionContext


@dataclass(frozen=True)
class PreparedParticipantControlTransition:
    """Uncommitted RUN-310 transition for composition with RUN-319."""

    next_snapshot: RuntimeSnapshot
    record: ControlPlaneOperationRecord
    audit_event: AuditEvent
    expected_control_head: str | None
    bound: _BoundControlRequest


def record_participant_control(
    control_plane: object,
    *,
    participant_address: str,
    intent: ParticipantControlIntent,
    identity: object,
    idempotency_key: str,
) -> OperationReceipt:
    """Bind, validate, and atomically append one supervisory occurrence."""

    if not isinstance(identity, ControlPlaneIdentity):
        raise PermissionError("participant control requires an authenticated identity")
    if identity.target_name is not None and identity.target_name != control_plane.target_name:
        raise PermissionError("participant control identity is not authorized for this target")
    _require_participant_binding(identity, participant_address)
    with (
        control_plane_mutation(control_plane, OperationKind.PARTICIPANT_CONTROL),
        control_plane._participant_control_lock,
    ):
        control_plane._reload_derived_state()
        bound = bind_participant_control_request(
            control_plane,
            participant_address,
            intent,
            identity,
            idempotency_key,
        )
        existing = control_plane._store.find_by_idempotency(bound.scoped_key) if bound.scoped_key else None
        if existing is not None:
            if existing.request_fingerprint != bound.semantic_fingerprint:
                raise ValueError("Idempotency-Key was reused with different semantics.")
            control_plane._operations[existing.receipt.operation_id] = existing
            return existing.receipt
        prepared = prepare_participant_control_transition(
            control_plane,
            participant_address,
            intent,
            identity,
            bound,
        )
        running = replace(
            prepared.record,
            status=replace(
                prepared.record.status,
                state=OperationState.RUNNING,
                diagnostics=[],
                changed_addresses=[],
            ),
        )
        claimed = control_plane._claim_record(running)
        if claimed.receipt.operation_id != running.receipt.operation_id:
            return claimed.receipt
        control_plane._commit_control_transition(
            participant_address=participant_address,
            expected_head=prepared.expected_control_head,
            snapshot=prepared.next_snapshot,
            record=prepared.record,
            audit_event=prepared.audit_event,
        )
        return prepared.record.receipt


def bind_participant_control_request(
    control_plane: object,
    participant_address: str,
    intent: ParticipantControlIntent,
    identity: ControlPlaneIdentity,
    idempotency_key: str,
) -> _BoundControlRequest:
    specification = _specification_for_participant(control_plane, participant_address, identity)
    transition = _transition_for_intent(specification, intent, identity)
    state = _state_by_address(specification, transition.from_state_address)
    return _BoundControlRequest(
        specification=specification,
        transition=transition,
        state=state,
        semantic_fingerprint=_semantic_fingerprint(
            control_plane,
            participant_address,
            intent,
            identity,
            specification,
            transition,
        ),
        scoped_key=_scoped_idempotency_key(
            control_plane,
            participant_address,
            intent,
            identity,
            idempotency_key,
        ),
        context=operation_admission_context(
            control_plane,
            kind=OperationKind.PARTICIPANT_CONTROL,
            request=intent,
            identity=identity,
            run_scope=f"run:{intent.episode_id}",
        ),
    )


def prepare_participant_control_transition(
    control_plane: object,
    participant_address: str,
    intent: ParticipantControlIntent,
    identity: ControlPlaneIdentity,
    bound: _BoundControlRequest,
) -> PreparedParticipantControlTransition:
    history = list(control_plane._snapshot.participant_control_history.get(participant_address, ()))
    current_state, current_revision = _fold_controller_state(
        bound.specification,
        history,
        episode_id=intent.episode_id,
    )
    resolved_target, target_rejection_reason = resolve_participant_control_target(
        control_plane._snapshot,
        intent,
        participant_address=participant_address,
    )
    rejection_reason = participant_control_rejection_reason(
        bound.specification,
        bound.transition,
        bound.state,
        intent,
        current_state=current_state,
        current_revision=current_revision,
        target_rejection_reason=target_rejection_reason,
    )
    accepted = rejection_reason is None
    occurrence = build_participant_control_occurrence(
        ParticipantControlOccurrenceContext(
            control_plane=control_plane,
            participant_address=participant_address,
            specification=bound.specification,
            transition=bound.transition,
            state=bound.state,
            history=history,
        ),
        intent,
        resolved_target=resolved_target,
        accepted=accepted,
        rejection_reason=rejection_reason,
    )
    candidate_history = [*history, occurrence.model_dump(mode="json")]
    _validate_candidate_history(
        bound.specification,
        candidate_history,
        known_targets=participant_control_target_contexts(control_plane._snapshot),
    )
    next_snapshot = control_plane._snapshot.with_entries(
        dict(control_plane._snapshot.entries),
        participant_control_history={
            **control_plane._snapshot.participant_control_history,
            participant_address: candidate_history,
        },
    )
    record, audit_event = participant_control_operation_artifacts(
        participant_address=participant_address,
        intent=intent,
        occurrence=occurrence,
        accepted=accepted,
        rejection_reason=rejection_reason,
        authority=ParticipantControlOperationAuthority(
            identity=identity,
            context=bound.context,
            semantic_fingerprint=bound.semantic_fingerprint,
            scoped_key=bound.scoped_key,
        ),
    )
    return PreparedParticipantControlTransition(
        next_snapshot=next_snapshot,
        record=record,
        audit_event=audit_event,
        expected_control_head=_history_head(history),
        bound=bound,
    )


def _specification_for_participant(
    control_plane: object,
    participant_address: str,
    identity: ControlPlaneIdentity,
) -> ParticipantBehaviorSpecificationRuntime:
    authorized_controllers = _authorized_controller_refs(identity, participant_address)
    candidates = [
        specification
        for specification in control_plane._behavior_specifications.values()
        if specification.mixed_control_participant_address == participant_address
        and any(state.controller_address in authorized_controllers for state in specification.controller_states)
    ]
    if len(candidates) != 1:
        raise ValueError("participant must resolve exactly one trusted mixed-control specification")
    return candidates[0]


def _transition_for_intent(
    specification: ParticipantBehaviorSpecificationRuntime,
    intent: ParticipantControlIntent,
    identity: ControlPlaneIdentity,
) -> MixedControlTransitionRuntime:
    authorized_controllers = _authorized_controller_refs(
        identity,
        specification.mixed_control_participant_address,
    )
    states = {state.address: state for state in specification.controller_states}
    candidates = [
        transition
        for transition in specification.control_transitions
        if transition.address == intent.declaration_ref
        and transition.transition_kind == intent.kind
        and transition.from_state_address in states
        and states[transition.from_state_address].controller_address in authorized_controllers
    ]
    if len(candidates) != 1:
        raise ValueError("control intent must resolve exactly one compiled transition")
    return candidates[0]


def _state_by_address(
    specification: ParticipantBehaviorSpecificationRuntime,
    address: str,
) -> MixedControlControllerStateRuntime:
    candidates = [state for state in specification.controller_states if state.address == address]
    if len(candidates) != 1:
        raise ValueError("compiled controller state must resolve exactly once")
    return candidates[0]


def _require_participant_binding(
    identity: ControlPlaneIdentity,
    participant_address: str,
) -> None:
    if not _authorized_controller_refs(identity, participant_address):
        raise PermissionError("participant control subject is not authorized")


def _authorized_controller_refs(
    identity: ControlPlaneIdentity,
    participant_address: str,
) -> frozenset[str]:
    return frozenset(
        binding.controller_ref
        for binding in identity.participant_control_subjects
        if binding.participant_address == participant_address
    )


def _fold_controller_state(
    specification: ParticipantBehaviorSpecificationRuntime,
    history: list[dict[str, object]],
    *,
    episode_id: str,
) -> tuple[str, int]:
    state_address = specification.mixed_control_initial_state_address
    revision = 0
    transitions = {transition.address: transition for transition in specification.control_transitions}
    for payload in history:
        event = ParticipantControlOccurrenceModel.model_validate(payload)
        if event.episode_id != episode_id:
            continue
        if event.occurrence.disposition is not ParticipantControlDisposition.ACCEPTED:
            continue
        transition = transitions.get(event.occurrence.declaration_ref)
        if transition is None:
            raise ValueError("control history references an unknown compiled transition")
        if transition.from_state_address != state_address or transition.expected_state_revision != revision:
            raise ValueError("control history does not replay from compiled controller state")
        state_address = transition.to_state_address
        revision = transition.resulting_state_revision
    return state_address, revision


def _history_head(history: list[dict[str, object]]) -> str | None:
    if not history:
        return None
    value = history[-1].get("event_id")
    return value if isinstance(value, str) and value else None


def _declaration(
    specification: ParticipantBehaviorSpecificationRuntime,
    transition: MixedControlTransitionRuntime,
    episode_id: str,
) -> ParticipantControlDeclarationModel:
    state = _state_by_address(specification, transition.from_state_address)
    return ParticipantControlDeclarationModel.model_validate(
        {
            "declaration_ref": transition.address,
            "kind": transition.transition_kind,
            "participant_address": specification.mixed_control_participant_address,
            "episode_id": episode_id,
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
        }
    )


def _validate_candidate_history(
    specification: ParticipantBehaviorSpecificationRuntime,
    history: list[dict[str, object]],
    *,
    known_targets: tuple[ParticipantControlTargetContextModel, ...],
) -> None:
    records = [ParticipantControlOccurrenceModel.model_validate(payload) for payload in history]
    transitions = {transition.address: transition for transition in specification.control_transitions}
    declarations = [
        _declaration(
            specification,
            transitions[record.occurrence.declaration_ref],
            record.episode_id,
        )
        for record in records
    ]
    validate_participant_control_occurrence_context(
        records,
        declarations=declarations,
        known_targets=known_targets,
    )


def _semantic_fingerprint(
    control_plane: object,
    participant_address: str,
    intent: ParticipantControlIntent,
    identity: ControlPlaneIdentity,
    specification: ParticipantBehaviorSpecificationRuntime,
    transition: MixedControlTransitionRuntime,
) -> str:
    payload = {
        "target": control_plane.target_name,
        "identity": identity.identity,
        "participant": participant_address,
        "intent": intent.model_dump(mode="json"),
        "specification": specification.address,
        "transition": asdict(transition),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _scoped_idempotency_key(
    control_plane: object,
    participant_address: str,
    intent: ParticipantControlIntent,
    identity: ControlPlaneIdentity,
    idempotency_key: str,
) -> str:
    if not idempotency_key:
        return ""
    scope = (
        control_plane.target_name,
        identity.identity,
        intent.kind,
        participant_address,
        intent.episode_id,
        idempotency_key,
    )
    digest = hashlib.sha256("\x1f".join(scope).encode()).hexdigest()
    return f"participant-control:{digest}"


__all__ = (
    "PreparedParticipantControlTransition",
    "bind_participant_control_request",
    "prepare_participant_control_transition",
    "record_participant_control",
)

"""Bounded phase progression for an admitted mixed runtime binding."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from raes_contracts.contracts.mixed_composition import MixedCompositionTransitionModel
from raes_contracts.contracts.mixed_runtime import (
    MixedCompositionRuntimeEventModel,
    MixedCompositionRuntimeStateModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import AuthorizationError, ConflictError
from raes_contracts.operation_lifecycle import OperationAdmissionContext
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationReceipt,
    OperationState,
    OperationStatus,
    operation_terminal_diagnostics,
)
from raes_contracts.timestamps import isoformat_z

from .control_plane_mutation import external_control_plane_call
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .mixed_runtime import MixedPhaseTransitionEvaluation, MixedRuntimeBinding
from .mixed_runtime_handoff_execution import _HandoffResolution, _perform_handoff
from .mixed_runtime_state import append_runtime_events, runtime_state
from .operation_reconciliation_ledger import valid_reconciliation_child

_OUTSTANDING_STATES = {OperationState.ACCEPTED, OperationState.RUNNING, OperationState.INDETERMINATE}
_LOGGER = get_logger(__name__)

if TYPE_CHECKING:
    from .mixed_backend_invocation import MixedInvocation


def _mixed_runtime_is_quiescent(control_plane: object, run_id: str, history_key: str) -> bool:
    """Read the authoritative operation ledger for unresolved mixed effects."""

    run_scope = f"run:{run_id}"
    records = tuple(control_plane._store.load_records().values())
    for record in records:
        if any(valid_reconciliation_child(record, child) for child in records):
            continue
        context = record.status.context
        if context.run_scope == run_scope and (
            (record.invocation is not None and record.invocation.reserved)
            or (
                record.status.state in _OUTSTANDING_STATES
                and (history_key in record.decision_history_heads or history_key in record.result_history_heads)
            )
        ):
            return False
    return True


def _evaluate(
    control_plane: object,
    transition: object,
    state: object,
    invocation: MixedInvocation | None = None,
) -> MixedPhaseTransitionEvaluation:
    binding = control_plane._mixed_runtime
    evaluator = binding.transition_evaluators[transition.evaluator_ref]
    try:
        if invocation is not None:
            from .mixed_backend_invocation import _external

            evaluation = _external(
                control_plane,
                invocation,
                evaluator,
                transition,
                state,
                control_plane._snapshot,
                limit=control_plane._supervision.admission_ms,
            )
        else:
            with external_control_plane_call(control_plane):
                evaluation = evaluator(deepcopy(transition), deepcopy(state), deepcopy(control_plane._snapshot))
    # Isolation: the admitted transition evaluator is an installed extension.
    except Exception as exc:
        _LOGGER.exception("mixed phase transition evaluator failed", exc_info=foreign_failure_record(exc))
        evaluation = _failed_evaluation("order:evaluator-failed")
    if isinstance(evaluation, MixedPhaseTransitionEvaluation):
        required = {item.evidence_ref for item in transition.evidence_bindings}
        valid = (
            1 <= evaluation.attempts <= transition.progress_bound
            and bool(evaluation.order_ref)
            and required.issubset(evaluation.evidence_refs)
        )
        if not valid:
            attempts = min(max(evaluation.attempts, 1), transition.progress_bound)
            evaluation = _failed_evaluation("order:evaluator-invalid", attempts)
    else:
        evaluation = _failed_evaluation("order:evaluator-invalid")
    return evaluation


def _failed_evaluation(order_ref: str, attempts: int = 1) -> MixedPhaseTransitionEvaluation:
    return MixedPhaseTransitionEvaluation(
        permitted=False,
        attempts=attempts,
        order_ref=order_ref,
        evidence_refs=(),
    )


def _phase_binding(
    control_plane: object,
    transition_id: str,
    identity: object,
) -> tuple[MixedRuntimeBinding, MixedCompositionTransitionModel]:
    if not isinstance(identity, ControlPlaneIdentity):
        raise AuthorizationError("mixed phase transition requires an authenticated identity")
    if identity.target_name is not None and identity.target_name != control_plane.target_name:
        raise AuthorizationError("mixed phase transition identity is not authorized for this target")
    binding = control_plane._mixed_runtime
    if binding is None:
        raise ConflictError("mixed runtime is not configured")
    transition = binding.profile.transitions.get(transition_id)
    if transition is None:
        raise ConflictError("mixed phase transition is not admitted")
    return binding, transition


def _phase_operation(
    control_plane: object,
    binding: MixedRuntimeBinding,
    transition_id: str,
    identity: ControlPlaneIdentity,
    idempotency_key: str,
    state: MixedCompositionRuntimeStateModel,
    history_key: str,
) -> tuple[OperationReceipt, ControlPlaneOperationRecord, OperationAdmissionContext]:
    context = operation_admission_context(
        control_plane,
        kind=control_plane._composition_operation_kind,
        request={
            "action": "advance",
            "transition_id": transition_id,
            "profile_digest": binding.profile.profile_digest,
        },
        identity=identity,
    )
    operation_id = str(uuid4())
    timestamp = isoformat_z(control_plane.wall_clock())
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=RuntimeDomain.PARTICIPANT,
        submitted_at=timestamp,
        accepted=True,
        context=context,
    )
    running = ControlPlaneOperationRecord(
        receipt=receipt,
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            state=OperationState.RUNNING,
            submitted_at=timestamp,
            updated_at=timestamp,
            context=context,
        ),
        idempotency_key=idempotency_key,
        request_fingerprint=context.request_commitment,
        decision_history_heads={history_key: state.history_head},
        result_history_heads={history_key: state.history_head},
    )
    return receipt, running, context


def _phase_event_fields(
    state: MixedCompositionRuntimeStateModel,
    transition: MixedCompositionTransitionModel,
    evaluation: MixedPhaseTransitionEvaluation,
) -> dict[str, object]:
    return {
        "run_id": state.run_id,
        "plan_id": state.plan_id,
        "plan_entry_id": state.plan_entry_id,
        "profile_id": state.profile_id,
        "profile_digest": state.profile_digest,
        "control_event_ref": transition.trigger_ref,
        "order_ref": evaluation.order_ref,
        "evidence_refs": list(evaluation.evidence_refs),
        "provenance_refs": list(evaluation.provenance_refs),
    }


def _phase_outcome(
    binding: MixedRuntimeBinding,
    transition: MixedCompositionTransitionModel,
    state: MixedCompositionRuntimeStateModel,
    evaluation: MixedPhaseTransitionEvaluation,
    operation_id: str,
    handoff: _HandoffResolution | None,
) -> tuple[list[MixedCompositionRuntimeEventModel], OperationState, Diagnostic | None]:
    common = _phase_event_fields(state, transition, evaluation)
    target = binding.profile.phases[transition.target_phase_id]
    needs_handoff = set(state.active_component_ids) != set(target.active_component_ids)
    if not evaluation.permitted or (
        needs_handoff and handoff is not None and handoff.state is not OperationState.SUCCEEDED
    ):
        return _denied_phase_outcome(state, evaluation, operation_id, handoff, common)
    phase = MixedCompositionRuntimeEventModel(
        event_id=f"composition:{operation_id}:phase",
        event_kind="phase-transition",
        disposition="committed",
        predecessor_event_id=state.history_head,
        phase_id=target.phase_id,
        phase_revision=state.phase_revision + 1,
        active_component_ids=target.active_component_ids,
        active_allocation_ids=target.active_allocation_ids,
        active_edge_ids=target.active_edge_ids,
        **common,
    )
    if not needs_handoff:
        return [phase], OperationState.SUCCEEDED, None
    assert handoff is not None
    event = phase.model_copy(
        update={
            "event_id": f"composition:{operation_id}:handoff",
            "event_kind": "handoff",
            "predecessor_event_id": phase.event_id,
            "component_id": handoff.destination_component_id,
            "order_ref": handoff.order_ref,
            "evidence_refs": list(handoff.evidence_refs),
        }
    )
    return [phase, event], OperationState.SUCCEEDED, None


def _denied_phase_outcome(
    state: MixedCompositionRuntimeStateModel,
    evaluation: MixedPhaseTransitionEvaluation,
    operation_id: str,
    handoff: _HandoffResolution | None,
    common: dict[str, object],
) -> tuple[list[MixedCompositionRuntimeEventModel], OperationState, Diagnostic]:
    terminal_state = handoff.state if handoff is not None else OperationState.FAILED
    if evaluation.permitted and handoff is not None:
        common["order_ref"] = handoff.order_ref
        common["evidence_refs"] = list(dict.fromkeys([*evaluation.evidence_refs, *handoff.evidence_refs]))
    failure = MixedCompositionRuntimeEventModel(
        event_id=f"composition:{operation_id}:failure",
        event_kind="failure",
        disposition="indeterminate" if terminal_state is OperationState.INDETERMINATE else "denied",
        predecessor_event_id=state.history_head,
        phase_id=state.phase_id,
        phase_revision=state.phase_revision,
        active_component_ids=state.active_component_ids,
        active_allocation_ids=state.active_allocation_ids,
        active_edge_ids=state.active_edge_ids,
        **common,
    )
    diagnostic = Diagnostic(
        code="runtime.mixed-composition-transition-denied",
        domain="runtime",
        address=f"mixed-composition.{state.run_id}",
        message="The admitted phase transition or required executable handoff did not permit progression.",
    )
    return [failure], terminal_state, diagnostic


def advance_mixed_composition(
    control_plane: object,
    *,
    transition_id: str,
    identity: object,
    idempotency_key: str,
) -> OperationReceipt:
    """Evaluate and commit exactly one pre-admitted forward transition."""

    binding, transition = _phase_binding(control_plane, transition_id, identity)
    control_plane._reload_derived_state()
    state = runtime_state(binding, control_plane._snapshot)
    history_key = f"mixed_composition_history:{state.run_id}"
    receipt, running, context = _phase_operation(
        control_plane, binding, transition_id, identity, idempotency_key, state, history_key
    )
    running, invocation, refusal = _prepare_phase_start(
        control_plane,
        binding,
        transition_id,
        running,
        context,
        idempotency_key,
    )
    if refusal is not None:
        return refusal
    operation_id = receipt.operation_id
    source_matches = state.phase_id == transition.source_phase_id
    quiescent = _mixed_runtime_is_quiescent(control_plane, state.run_id, history_key)
    claimed = control_plane._claim_record(
        running,
        new_claim_blocked="current-state" if not source_matches or not quiescent else None,
    )
    if claimed.receipt.operation_id != operation_id:
        return claimed.receipt
    evaluation = _evaluate(control_plane, transition, state, invocation)
    handoff = _execute_phase_handoff(control_plane, binding, transition, state, operation_id, evaluation, invocation)
    events, terminal_state, diagnostic = _phase_outcome(binding, transition, state, evaluation, operation_id, handoff)
    snapshot = append_runtime_events(binding, control_plane._snapshot, state, events)
    terminal = replace(
        running,
        status=replace(
            running.status,
            state=terminal_state,
            updated_at=isoformat_z(control_plane.wall_clock()),
            diagnostics=operation_terminal_diagnostics(terminal_state, [] if diagnostic is None else [diagnostic]),
        ),
        result_history_heads={history_key: events[-1].event_id},
    )
    if invocation is not None:
        from .mixed_backend_action import retain_mixed_invocation

        terminal = retain_mixed_invocation(control_plane, cast(ControlPlaneOperationRecord, terminal), invocation)
    audit = AuditEvent(
        timestamp=terminal.status.updated_at,
        action="advance_mixed_composition",
        identity=context.actor_id,
        allowed=terminal_state is OperationState.SUCCEEDED,
        target=context.target_scope,
        operation_id=operation_id,
        reason="committed" if terminal_state is OperationState.SUCCEEDED else "transition-denied",
    )
    control_plane._commit_participant_transition(
        expected_history_heads={history_key: state.history_head},
        snapshot=snapshot,
        record=terminal,
        audit_event=audit,
    )
    return receipt


def _prepare_phase_start(
    plane: object,
    binding: MixedRuntimeBinding,
    transition_id: str,
    running: ControlPlaneOperationRecord,
    context: OperationAdmissionContext,
    idempotency_key: str,
) -> tuple[ControlPlaneOperationRecord, MixedInvocation | None, OperationReceipt | None]:
    if idempotency_key:
        from .control_plane_store import _require_same_idempotency_replay

        existing = plane._store.find_by_idempotency(idempotency_key, context=context)
        if existing is not None:
            _require_same_idempotency_replay(existing, running)
            return running, None, existing.receipt
    portable = next(
        (
            item
            for item in binding.backend_installations.values()
            if item.binding.subject.kind == "handoff" and item.binding.subject.transition_id == transition_id
        ),
        None,
    )
    invocation, refusal = None, None
    if portable is not None:
        from .mixed_backend_invocation import prepare_mixed_invocation, reject_mixed_admission

        invocation = prepare_mixed_invocation(plane, portable, running, plane._snapshot)
        if invocation is None:
            refusal = reject_mixed_admission(plane, running)
        else:
            running = replace(running, invocation=invocation.ledger.model_copy(update={"consumed": True}))
    return running, invocation, refusal


def _execute_phase_handoff(
    plane: object,
    binding: MixedRuntimeBinding,
    transition: MixedCompositionTransitionModel,
    state: MixedCompositionRuntimeStateModel,
    operation_id: str,
    evaluation: MixedPhaseTransitionEvaluation,
    invocation: MixedInvocation | None,
) -> _HandoffResolution | None:
    if invocation is None:
        return _perform_handoff(plane, binding, transition, state, operation_id) if evaluation.permitted else None
    from .mixed_backend_invocation import confirm_no_dispatch, run_mixed_invocation

    if evaluation.permitted:
        run_mixed_invocation(plane, invocation)
    else:
        invocation.state = OperationState.INDETERMINATE if invocation.uncertain else OperationState.FAILED
        if not invocation.uncertain:
            confirm_no_dispatch(invocation)
    return _portable_handoff_resolution(invocation)


def _portable_handoff_resolution(invocation: MixedInvocation) -> _HandoffResolution:
    reports = [item.stage for item in invocation.ledger.mixed_reports]
    grant = next((stage for stage in reports if stage.stage == "time-grant"), None)
    refs = tuple(dict.fromkeys(ref for stage in reports for ref in getattr(stage, "evidence_refs", ())))
    return _HandoffResolution(
        invocation.state,
        grant.order_ref if grant else "order:handoff-refused",
        refs,
        invocation.installation.binding.subject.destination_component_id
        if invocation.state is OperationState.SUCCEEDED
        else None,
    )

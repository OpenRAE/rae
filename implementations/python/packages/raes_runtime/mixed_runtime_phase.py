"""Bounded phase progression for an admitted mixed runtime binding."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from fractions import Fraction
from uuid import uuid4

from raes_contracts.contracts.mixed_composition import MixedCompositionTransitionModel
from raes_contracts.contracts.mixed_runtime import (
    MixedCompositionRuntimeEventModel,
    MixedCompositionRuntimeStateModel,
)
from raes_contracts.contracts.time_model import TimeRuntimeStateModel, validate_time_runtime_state
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.operation_lifecycle import OperationAdmissionContext
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    operation_terminal_diagnostics,
)

from .control_plane_execution import _utc_now
from .control_plane_mutation import external_control_plane_call
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity
from .control_plane_store import AuditEvent, ControlPlaneOperationRecord
from .mixed_runtime import MixedPhaseTransitionEvaluation, MixedRuntimeBinding
from .mixed_runtime_edge import MixedTimeCoordinationEvidence
from .mixed_runtime_handoff import MixedHandoffEvidence, MixedHandoffReadback
from .mixed_runtime_state import append_runtime_events, runtime_state

_OUTSTANDING_STATES = {OperationState.ACCEPTED, OperationState.RUNNING, OperationState.INDETERMINATE}


@dataclass(frozen=True)
class _HandoffResolution:
    state: OperationState
    order_ref: str
    evidence_refs: tuple[str, ...] = ()
    destination_component_id: str | None = None


def _mixed_runtime_is_quiescent(control_plane: object, run_id: str, history_key: str) -> bool:
    """Read the authoritative operation ledger for unresolved mixed effects."""

    run_scope = f"run:{run_id}"
    for record in control_plane._store.load_records().values():
        context = record.status.context
        if (
            context.run_scope == run_scope
            and context.operation_kind
            in {OperationKind.PARTICIPANT_ACTION, OperationKind.PARTICIPANT_CROSSING, OperationKind.COMPOSITION_PHASE}
            and record.status.state in _OUTSTANDING_STATES
            and (history_key in record.decision_history_heads or history_key in record.result_history_heads)
        ):
            return False
    return True


def _evaluate(control_plane: object, transition: object, state: object) -> MixedPhaseTransitionEvaluation:
    binding = control_plane._mixed_runtime
    evaluator = binding.transition_evaluators[transition.evaluator_ref]
    try:
        with external_control_plane_call(control_plane):
            evaluation = evaluator(deepcopy(transition), deepcopy(state), deepcopy(control_plane._snapshot))
    except Exception:
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
        raise PermissionError("mixed phase transition requires an authenticated identity")
    if identity.target_name is not None and identity.target_name != control_plane.target_name:
        raise PermissionError("mixed phase transition identity is not authorized for this target")
    binding = control_plane._mixed_runtime
    if binding is None:
        raise ValueError("mixed runtime is not configured")
    transition = binding.profile.transitions.get(transition_id)
    if transition is None:
        raise ValueError("mixed phase transition is not admitted")
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
    timestamp = _utc_now()
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


def _perform_handoff(
    control_plane: object,
    binding: MixedRuntimeBinding,
    transition: MixedCompositionTransitionModel,
    state: MixedCompositionRuntimeStateModel,
    operation_id: str,
) -> _HandoffResolution | None:
    target = binding.profile.phases[transition.target_phase_id]
    if set(state.active_component_ids) == set(target.active_component_ids):
        return None
    installed = binding.handoff_bindings.get(transition.transition_id)
    if installed is None:
        return _HandoffResolution(OperationState.FAILED, "order:handoff-unbound")
    declaration = binding.context.time_models[installed.time_model_ref]
    baseline_snapshot = deepcopy(control_plane._snapshot)
    try:
        with external_control_plane_call(control_plane):
            time_state = installed.time_runtime.state(deepcopy(baseline_snapshot))
            if not isinstance(time_state, TimeRuntimeStateModel):
                raise TypeError("handoff time readback must be typed")
            validate_time_runtime_state(declaration, time_state)
            if time_state != baseline_snapshot.time_model_state:
                raise ValueError("handoff time readback differs from the committed snapshot")
            grant = MixedTimeCoordinationEvidence.model_validate(
                installed.coordinate(operation_id, deepcopy(transition), deepcopy(time_state))
            )
        _require_handoff_time_grant(installed, grant, operation_id, declaration, time_state, transition)
    except Exception:
        return _HandoffResolution(OperationState.FAILED, "order:handoff-time-refused")
    grant_refs = tuple(dict.fromkeys([*grant.mapping_evidence_refs, *grant.timing_evidence_refs]))
    confirmed_refs = grant_refs
    required = {item.evidence_ref for item in transition.evidence_bindings}
    try:
        with external_control_plane_call(control_plane):
            evidence = MixedHandoffEvidence.model_validate(
                installed.invoke(operation_id, deepcopy(transition), deepcopy(state), deepcopy(baseline_snapshot))
            )
            correlated = (
                evidence.operation_id == operation_id
                and evidence.transition_id == transition.transition_id
                and evidence.source_component_id == installed.source_component_id
                and evidence.destination_component_id == installed.destination_component_id
                and evidence.predecessor_history_head == state.history_head
                and evidence.phase_revision == state.phase_revision
                and evidence.order_ref == grant.order_ref
                and required.issubset(evidence.evidence_refs)
            )
            if correlated:
                confirmed_refs = tuple(dict.fromkeys([*confirmed_refs, *evidence.evidence_refs]))
            readback = MixedHandoffReadback.model_validate(
                installed.readback(operation_id, deepcopy(baseline_snapshot))
            )
            if correlated and readback.operation_id == operation_id:
                confirmed_refs = tuple(dict.fromkeys([*confirmed_refs, *readback.evidence_refs]))
            final_time = installed.time_runtime.state(deepcopy(baseline_snapshot))
            if not isinstance(final_time, TimeRuntimeStateModel):
                raise TypeError("handoff post-transfer time readback must be typed")
            validate_time_runtime_state(declaration, final_time)
            if final_time != baseline_snapshot.time_model_state:
                raise ValueError("handoff post-transfer time readback differs from the committed snapshot")
            for clock_address in (installed.source_clock_address, installed.destination_clock_address):
                previous = time_state.clocks[clock_address].coordinate
                current = final_time.clocks[clock_address].coordinate
                if (current.segment, current.tick, current.microstep) < (
                    previous.segment,
                    previous.tick,
                    previous.microstep,
                ):
                    raise ValueError("handoff time readback regressed")
    except Exception:
        return _HandoffResolution(OperationState.INDETERMINATE, grant.order_ref, confirmed_refs)
    if not correlated or readback.operation_id != operation_id:
        return _HandoffResolution(OperationState.INDETERMINATE, grant.order_ref, confirmed_refs)
    combined = confirmed_refs
    if evidence.status == "committed":
        committed = (
            readback.owner_component_id == installed.destination_component_id
            and readback.owner_ref == installed.destination_owner_ref
            and readback.phase_revision == state.phase_revision + 1
        )
        return _HandoffResolution(
            OperationState.SUCCEEDED if committed else OperationState.INDETERMINATE,
            evidence.order_ref,
            combined,
            installed.destination_component_id if committed else None,
        )
    if evidence.status in {"failed", "stale"}:
        retained = (
            readback.owner_component_id == installed.source_component_id
            and readback.owner_ref == installed.source_owner_ref
            and readback.phase_revision == state.phase_revision
        )
        return _HandoffResolution(
            OperationState.FAILED if retained else OperationState.INDETERMINATE,
            evidence.order_ref,
            combined,
        )
    return _HandoffResolution(OperationState.INDETERMINATE, evidence.order_ref, combined)


def _require_handoff_time_grant(
    installed: object,
    grant: MixedTimeCoordinationEvidence,
    operation_id: str,
    declaration: object,
    state: TimeRuntimeStateModel,
    transition: MixedCompositionTransitionModel,
) -> None:
    source = state.clocks[installed.source_clock_address].coordinate
    destination = state.clocks[installed.destination_clock_address].coordinate
    mapping = declaration.mappings[installed.mapping_ref]
    mapped_tick = Fraction(source.tick * mapping.scale.numerator, mapping.scale.denominator) + mapping.offset_ticks
    required = {item.evidence_ref for item in transition.evidence_bindings}
    if (
        grant.operation_id != operation_id
        or grant.mapping_ref != installed.mapping_ref
        or grant.ordering_basis != installed.ordering_basis
        or grant.comparison != "ordered"
        or grant.source_coordinate != source
        or grant.destination_coordinate != destination
        or source.segment != destination.segment
        or (mapped_tick, source.microstep) > (destination.tick, destination.microstep)
        or not required.issubset(set(grant.mapping_evidence_refs) | set(grant.timing_evidence_refs))
    ):
        raise ValueError("handoff time coordination is unsupported")


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
        terminal_state = handoff.state if evaluation.permitted and handoff is not None else OperationState.FAILED
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
    operation_id = receipt.operation_id
    source_matches = state.phase_id == transition.source_phase_id
    quiescent = _mixed_runtime_is_quiescent(control_plane, state.run_id, history_key)
    claimed = control_plane._claim_record(
        running,
        new_claim_blocked="current-state" if not source_matches or not quiescent else None,
    )
    if claimed.receipt.operation_id != operation_id:
        return claimed.receipt
    evaluation = _evaluate(control_plane, transition, state)
    handoff = (
        _perform_handoff(control_plane, binding, transition, state, operation_id) if evaluation.permitted else None
    )
    events, terminal_state, diagnostic = _phase_outcome(binding, transition, state, evaluation, operation_id, handoff)
    snapshot = append_runtime_events(binding, control_plane._snapshot, state, events)
    terminal = replace(
        running,
        status=replace(
            running.status,
            state=terminal_state,
            updated_at=_utc_now(),
            diagnostics=operation_terminal_diagnostics(terminal_state, [] if diagnostic is None else [diagnostic]),
        ),
        result_history_heads={history_key: events[-1].event_id},
    )
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

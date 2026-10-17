"""Portable mixed stages pass the existing participant result and history boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, cast

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.mixed_runtime import MixedCompositionRuntimeEventModel
from raes_contracts.runtime_state import ApplyResult, OperationReceipt, OperationState, RuntimeSnapshot

from .control_plane_participant_apply import apply_authorized_participant_action
from .control_plane_store import ControlPlaneOperationRecord
from .control_plane_store_snapshots import _snapshot_payload
from .mixed_backend_invocation import MixedInvocation, _external, run_mixed_invocation
from .mixed_runtime_state import append_runtime_events, runtime_state

if TYPE_CHECKING:
    from raes_contracts.contracts.mixed_backend_stages import MixedBackendStage
    from raes_contracts.contracts.mixed_composition import MixedCompositionAllocationModel
    from raes_contracts.contracts.mixed_runtime import MixedCompositionRuntimeStateModel
    from raes_contracts.participant_binding import ParticipantActionAdmissionRequest

    from .control_plane import RuntimeControlPlane
    from .mixed_backend_installation import MixedBackendInstallation
    from .participant_crossing_boundary import _PreparedActionEffect
    from .participant_crossing_mediation import PreparedParticipantCrossing


def replay_action(plane: RuntimeControlPlane, crossing: PreparedParticipantCrossing) -> OperationReceipt | None:
    from .control_plane_store import _require_same_idempotency_replay

    if not crossing.record.idempotency_key:
        return None
    existing = plane._store.find_by_idempotency(
        crossing.record.idempotency_key, context=crossing.record.receipt.context
    )
    if existing is not None and existing.invocation is not None and existing.invocation.mixed_binding is not None:
        heads = dict(crossing.record.decision_history_heads)
        state = runtime_state(plane._mixed_runtime, plane._snapshot)
        heads[f"mixed_composition_history:{state.run_id}"] = state.history_head
        replay = cast(ControlPlaneOperationRecord, replace(crossing.record, decision_history_heads=heads))
        _require_same_idempotency_replay(existing, replay)
        return existing.receipt
    return None


def prepare_backend_action(
    plane: RuntimeControlPlane,
    portable: MixedBackendInstallation,
    crossing: PreparedParticipantCrossing,
    request: ParticipantActionAdmissionRequest,
    allocation: MixedCompositionAllocationModel,
) -> MixedInvocation | None:
    from .mixed_backend_invocation import prepare_mixed_invocation

    subject = portable.binding.subject
    if (subject.participant_address, subject.destination_action_address, subject.owner_allocation_id) != (
        request.participant_address,
        request.action_contract_address,
        allocation.allocation_id,
    ):
        raise ValueError("mixed portable binding differs from the governed action")
    return prepare_mixed_invocation(plane, portable, crossing.record, crossing.next_snapshot)


def apply_mixed_backend_action(plane: RuntimeControlPlane, prepared: _PreparedActionEffect) -> ApplyResult:
    execution = prepared.mixed_dispatch.invocation
    predecessor = deepcopy(plane._snapshot)
    run_mixed_invocation(plane, execution)
    result = ApplyResult(False, predecessor)
    reference = (
        None
        if execution.outcome is None
        else (execution.outcome.message.result or execution.outcome.message.effects.residual_state)
    )
    if execution.effects_verified and reference is not None:
        try:
            result = _validated_native_action(plane, prepared, predecessor, reference.contract_id, reference.digest)
            execution.native_validated = True
        except Exception:
            execution.state, execution.release_commitment = OperationState.INDETERMINATE, None
            result = ApplyResult(False, predecessor)
    elif execution.state is OperationState.SUCCEEDED:
        execution.state, execution.release_commitment = OperationState.INDETERMINATE, None
    return result


def _validated_native_action(
    plane: RuntimeControlPlane,
    prepared: _PreparedActionEffect,
    predecessor: RuntimeSnapshot,
    contract_id: str,
    digest: str,
) -> ApplyResult:
    execution = prepared.mixed_dispatch.invocation
    if execution.outcome is None:
        raise ValueError("mixed native result requires its invocation outcome")
    native = _external(
        plane,
        execution,
        execution.installation.evidence.resolve_result,
        execution.ledger.request,
        execution.outcome,
        predecessor,
        limit=plane._supervision.observation_ms,
    )
    if (
        not isinstance(native, ApplyResult)
        or contract_id != "runtime-snapshot-v1"
        or canonical_json_digest(_snapshot_payload(native.snapshot)) != digest
    ):
        raise ValueError("mixed native result commitment mismatch")
    result = _external(
        plane,
        execution,
        partial(
            apply_authorized_participant_action,
            method=lambda _request, _snapshot: native,
            request=prepared.request,
            snapshot=predecessor,
            address=prepared.mixed_dispatch.address,
            information_state_context_resolver=plane._information_state_context_resolver,
        ),
        limit=plane._supervision.observation_ms,
    )
    if canonical_json_digest(_snapshot_payload(result.snapshot)) != digest:
        raise ValueError("mixed native result was rejected")
    if execution.state is OperationState.SUCCEEDED and not result.success:
        raise ValueError("mixed native release gates failed")
    return result


def record_mixed_backend_action(
    plane: RuntimeControlPlane,
    snapshot: RuntimeSnapshot,
    prepared: _PreparedActionEffect,
) -> RuntimeSnapshot:
    execution = prepared.mixed_dispatch.invocation
    binding = plane._mixed_runtime
    state = runtime_state(binding, snapshot)
    attempt = snapshot.mixed_composition_history[state.run_id][-1]
    if attempt["event_id"] != f"composition:{execution.ledger.request.binding.operation_id}:attempt":
        raise ValueError("mixed result no longer owns the committed attempt")
    common = {
        key: attempt[key]
        for key in (
            "run_id",
            "plan_id",
            "plan_entry_id",
            "profile_id",
            "profile_digest",
            "phase_id",
            "phase_revision",
            "active_component_ids",
            "active_allocation_ids",
            "active_edge_ids",
            "allocation_id",
            "component_id",
            "edge_id",
            "control_event_ref",
            "crossing_event_ref",
            "policy_decision_ref",
            "mapping_ref",
            "order_ref",
        )
    }
    events = _action_events(execution, state, common)
    return append_runtime_events(binding, snapshot, state, events)


def _action_events(
    execution: MixedInvocation,
    state: MixedCompositionRuntimeStateModel,
    common: dict[str, object],
) -> list[MixedCompositionRuntimeEventModel]:
    stages = {report.stage.stage: report.stage for report in execution.ledger.mixed_reports}
    grant = stages.get("time-grant")
    if grant is not None and execution.post_time is not None:
        common["order_ref"] = grant.order_ref
    report = stages.get("execution")
    events = []
    for kind, disposition, refs in _stage_specifications(execution, stages):
        event = MixedCompositionRuntimeEventModel(
            event_id=f"composition:{execution.ledger.request.binding.operation_id}:{kind}",
            event_kind=kind,
            disposition=disposition,
            predecessor_event_id=events[-1].event_id if events else state.history_head,
            evidence_refs=refs,
            mapping_loss_refs=[] if report is None else list(report.mapping_loss_refs),
            **common,
        )
        events.append(event)
    return events


def _stage_specifications(
    execution: MixedInvocation,
    stages: dict[str, MixedBackendStage],
) -> list[tuple[str, str, list[str]]]:
    report = stages.get("execution")
    disposition = {OperationState.SUCCEEDED: "succeeded", OperationState.FAILED: "failed"}.get(
        execution.state, "indeterminate"
    )
    specifications = [
        (
            "result",
            disposition,
            [] if report is None else list(dict.fromkeys([*report.evidence_refs, *report.cessation_evidence_refs])),
        )
    ]
    if execution.native_validated and "delivery" in stages:
        specifications.append(("delivery", "succeeded", list(stages["delivery"].evidence_refs)))
    if execution.native_validated and "observation" in stages:
        specifications.append(("observation", "committed", list(stages["observation"].evidence_refs)))
    return specifications


def retain_mixed_invocation(
    plane: RuntimeControlPlane,
    record: ControlPlaneOperationRecord,
    execution: MixedInvocation,
) -> ControlPlaneOperationRecord:
    """Preserve concurrent controls and release only a fully validated terminal cut."""

    plane._reload_derived_state()
    current = plane._operations[record.receipt.operation_id]
    ledger = current.invocation
    if ledger.request.binding.owner_generation != plane._execution_generation:
        raise ValueError("stale mixed execution owner")
    released = not ledger.consumed or execution.release_commitment is not None
    ledger = ledger.model_copy(update={"reserved": not released, "release_commitment": execution.release_commitment})
    plane._execution_deadlines.pop(record.receipt.operation_id, None)
    return cast(ControlPlaneOperationRecord, replace(record, invocation=ledger))

"""Correlated mixed action stages and shared operation settlement."""

from __future__ import annotations

from typing import Literal

from raes_contracts.contracts.mixed_runtime import MixedCompositionRuntimeEventModel
from raes_contracts.runtime_state import ApplyResult, OperationState, RuntimeSnapshot

from .mixed_runtime_dispatch import PreparedMixedActionDispatch, _runtime_event_fields
from .mixed_runtime_edge import MixedEdgeExecutionCapture
from .mixed_runtime_state import append_runtime_events, runtime_state
from .participant_crossing_mediation import PreparedParticipantCrossing

_EventKind = Literal["result", "delivery", "observation", "weakening", "failure"]
_Disposition = Literal["committed", "succeeded", "failed", "indeterminate"]


def record_mixed_action_result(
    control_plane: object,
    snapshot: RuntimeSnapshot,
    crossing: PreparedParticipantCrossing,
    *,
    success: bool,
    capture: MixedEdgeExecutionCapture | None = None,
) -> RuntimeSnapshot:
    """Append the backend outcome without allowing it to rewrite the decision."""

    binding = getattr(control_plane, "_mixed_runtime", None)
    if binding is None:
        return snapshot
    state = runtime_state(binding, snapshot)
    attempt = snapshot.mixed_composition_history[state.run_id][-1]
    common = _runtime_event_fields(
        state,
        allocation_id=attempt.get("allocation_id"),
        component_id=attempt.get("component_id"),
        edge_id=attempt.get("edge_id"),
        control_event_ref=attempt.get("control_event_ref"),
        crossing_event_ref=attempt.get("crossing_event_ref"),
        policy_decision_ref=attempt.get("policy_decision_ref"),
        mapping_ref=attempt.get("mapping_ref"),
        order_ref=str(attempt["order_ref"]),
        mapping_loss_refs=[],
        evidence_refs=list(attempt.get("evidence_refs", [])),
    )
    operation_id = crossing.record.receipt.operation_id
    events: list[MixedCompositionRuntimeEventModel] = []

    def append(kind: _EventKind, disposition: _Disposition) -> None:
        predecessor = state.history_head if not events else events[-1].event_id
        events.append(
            MixedCompositionRuntimeEventModel(
                event_id=f"composition:{operation_id}:{kind}",
                event_kind=kind,
                disposition=disposition,
                predecessor_event_id=predecessor,
                **common,
            )
        )

    report = capture.bridge if capture is not None else None
    outcome = report.execution_status if report is not None else None
    rejected_result = capture is not None and capture.method_completed and not success
    unconfirmed_success = (
        outcome == "succeeded" and capture is not None and (capture.stage_readback_failed or not capture.time_confirmed)
    )
    if capture is not None and capture.provider_started and report is None:
        disposition: _Disposition = "indeterminate"
    elif outcome in {"partial", "unknown"} or (outcome == "succeeded" and rejected_result) or unconfirmed_success:
        disposition = "indeterminate"
    elif outcome == "succeeded":
        disposition = "succeeded"
    else:
        disposition = "succeeded" if success else "failed"
    if report is not None and not rejected_result and capture is not None and capture.time_confirmed:
        common["mapping_loss_refs"] = list(report.mapping_loss_refs)
    if capture is not None and capture.time is not None and not rejected_result:
        if capture.time_confirmed:
            common["order_ref"] = capture.time.order_ref
        common["evidence_refs"] = list(
            dict.fromkeys(
                [
                    *common["evidence_refs"],
                    *capture.time.mapping_evidence_refs,
                    *capture.time.timing_evidence_refs,
                    *(report.execution_evidence_refs if report is not None else ()),
                ]
            )
        )
    if report is not None and outcome == "failed" and capture is not None and capture.method_completed:
        common["evidence_refs"] = list(dict.fromkeys([*common["evidence_refs"], *report.cessation_evidence_refs]))
    append("result", disposition)
    if not rejected_result and report is not None and capture is not None and capture.delivery_confirmed:
        common["evidence_refs"] = list(report.delivery_evidence_refs)
        append("delivery", "succeeded")
    if not rejected_result and report is not None and capture is not None and capture.observation_confirmed:
        common["evidence_refs"] = list(report.observation_evidence_refs)
        append("observation", "committed")
    if (
        not rejected_result
        and report is not None
        and capture is not None
        and capture.time_confirmed
        and report.mapping_loss_refs
    ):
        common["evidence_refs"] = list(capture.time.mapping_evidence_refs) if capture.time is not None else []
        append("weakening", "committed")
    if disposition == "failed":
        append("failure", "failed")
    return append_runtime_events(binding, snapshot, state, events)


def mixed_action_terminal_state(
    dispatch: PreparedMixedActionDispatch | None,
    result: ApplyResult,
) -> OperationState:
    """Settle one mixed action from its correlated stages, not a success flag."""

    if dispatch is None or dispatch.capture is None:
        return OperationState.SUCCEEDED if result.success else OperationState.FAILED
    capture = dispatch.capture
    report = capture.bridge
    if report is None:
        return OperationState.INDETERMINATE if capture.provider_started else OperationState.FAILED
    if report.execution_status in {"partial", "unknown"}:
        return OperationState.INDETERMINATE
    if report.execution_status == "failed":
        return OperationState.FAILED
    if (
        not result.success
        or not capture.time_confirmed
        or capture.stage_readback_failed
        or not capture.delivery_confirmed
    ):
        return OperationState.INDETERMINATE
    return OperationState.SUCCEEDED


__all__ = ("mixed_action_terminal_state", "record_mixed_action_result")

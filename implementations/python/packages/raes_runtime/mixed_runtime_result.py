"""Correlated mixed action stages and shared operation settlement."""

from __future__ import annotations

from typing import Literal

from raes_contracts.contracts.mixed_runtime import MixedCompositionRuntimeEventModel
from raes_contracts.runtime_state import ApplyResult, OperationState, RuntimeSnapshot

from .mixed_runtime_dispatch import PreparedMixedActionDispatch, _runtime_event_fields
from .mixed_runtime_edge import MixedBridgeExecutionEvidence, MixedEdgeExecutionCapture
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
    report = capture.bridge if capture is not None else None
    rejected_result = capture is not None and capture.method_completed and not success
    disposition = _result_disposition(capture, report, success, rejected_result)
    _augment_result_evidence(common, capture, report, rejected_result)
    events = [_result_event(operation_id, "result", disposition, state.history_head, common)]
    _append_confirmed_stages(events, operation_id, common, capture, report, rejected_result)
    if disposition == "failed":
        events.append(_result_event(operation_id, "failure", "failed", events[-1].event_id, common))
    return append_runtime_events(binding, snapshot, state, events)


def _result_disposition(
    capture: MixedEdgeExecutionCapture | None,
    report: MixedBridgeExecutionEvidence | None,
    success: bool,
    rejected_result: bool,
) -> _Disposition:
    if _unconfirmed_execution(capture, report, rejected_result):
        disposition: _Disposition = "indeterminate"
    elif report is not None and report.execution_status == "succeeded":
        disposition = "succeeded"
    else:
        disposition = "succeeded" if success else "failed"
    return disposition


def _unconfirmed_execution(
    capture: MixedEdgeExecutionCapture | None,
    report: MixedBridgeExecutionEvidence | None,
    rejected_result: bool,
) -> bool:
    if report is None:
        unconfirmed = capture is not None and capture.provider_started
    elif report.execution_status in {"partial", "unknown"}:
        unconfirmed = True
    elif report.execution_status == "succeeded":
        unconfirmed = rejected_result or _unconfirmed_stages(capture)
    else:
        unconfirmed = False
    return unconfirmed


def _unconfirmed_stages(capture: MixedEdgeExecutionCapture | None) -> bool:
    return capture is not None and (capture.stage_readback_failed or not capture.time_confirmed)


def _augment_result_evidence(
    common: dict[str, object],
    capture: MixedEdgeExecutionCapture | None,
    report: MixedBridgeExecutionEvidence | None,
    rejected_result: bool,
) -> None:
    if capture is None:
        return
    if report is not None and not rejected_result and capture.time_confirmed:
        common["mapping_loss_refs"] = list(report.mapping_loss_refs)
    if capture.time is not None and not rejected_result:
        _append_time_evidence(common, capture, report)
    if report is not None and report.execution_status == "failed" and capture.method_completed:
        common["evidence_refs"] = list(dict.fromkeys([*common["evidence_refs"], *report.cessation_evidence_refs]))


def _append_time_evidence(
    common: dict[str, object],
    capture: MixedEdgeExecutionCapture,
    report: MixedBridgeExecutionEvidence | None,
) -> None:
    assert capture.time is not None
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


def _result_event(
    operation_id: str,
    kind: _EventKind,
    disposition: _Disposition,
    predecessor: str,
    common: dict[str, object],
) -> MixedCompositionRuntimeEventModel:
    return MixedCompositionRuntimeEventModel(
        event_id=f"composition:{operation_id}:{kind}",
        event_kind=kind,
        disposition=disposition,
        predecessor_event_id=predecessor,
        **common,
    )


def _append_confirmed_stages(
    events: list[MixedCompositionRuntimeEventModel],
    operation_id: str,
    common: dict[str, object],
    capture: MixedEdgeExecutionCapture | None,
    report: MixedBridgeExecutionEvidence | None,
    rejected_result: bool,
) -> None:
    if rejected_result or report is None or capture is None:
        return
    if capture.delivery_confirmed:
        common["evidence_refs"] = list(report.delivery_evidence_refs)
        events.append(_result_event(operation_id, "delivery", "succeeded", events[-1].event_id, common))
    if capture.observation_confirmed:
        common["evidence_refs"] = list(report.observation_evidence_refs)
        events.append(_result_event(operation_id, "observation", "committed", events[-1].event_id, common))
    if capture.time_confirmed and report.mapping_loss_refs:
        common["evidence_refs"] = list(capture.time.mapping_evidence_refs) if capture.time is not None else []
        events.append(_result_event(operation_id, "weakening", "committed", events[-1].event_id, common))


def mixed_action_terminal_state(
    dispatch: PreparedMixedActionDispatch | None,
    result: ApplyResult,
) -> OperationState:
    """Settle one mixed action from its correlated stages, not a success flag."""

    if dispatch is None or dispatch.capture is None:
        state = OperationState.SUCCEEDED if result.success else OperationState.FAILED
    else:
        state = _captured_action_terminal_state(dispatch.capture, result)
    return state


def _captured_action_terminal_state(capture: MixedEdgeExecutionCapture, result: ApplyResult) -> OperationState:
    report = capture.bridge
    if report is None:
        state = OperationState.INDETERMINATE if capture.provider_started else OperationState.FAILED
    elif report.execution_status in {"partial", "unknown"}:
        state = OperationState.INDETERMINATE
    elif report.execution_status == "failed":
        state = OperationState.FAILED
    else:
        confirmed = all(
            (result.success, capture.time_confirmed, not capture.stage_readback_failed, capture.delivery_confirmed)
        )
        state = OperationState.SUCCEEDED if confirmed else OperationState.INDETERMINATE
    return state


__all__ = ("mixed_action_terminal_state", "record_mixed_action_result")

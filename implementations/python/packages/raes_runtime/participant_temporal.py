"""Bounded guarantee checks against the existing shared-time authority."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal, cast

from raes_backend_protocols.participant_action_commit import participant_binding_post_state_digest
from raes_contracts.contracts import ParticipantActionResultModel, ParticipantBehaviorHistoryEventModel
from raes_contracts.contracts.participant_temporal import (
    ParticipantTemporalAssessmentModel,
    ParticipantTemporalEvidenceModel,
    ParticipantTemporalExecutionContextModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_behavior import ParticipantAdmissionDisposition
from raes_contracts.participant_binding import (
    ParticipantActionAdmissionRequest,
    ParticipantActionApplyResult,
    participant_action_binding_events,
    participant_behavior_event_payload,
)
from raes_contracts.participant_temporal import assess_temporal_guarantee, coordinate_key
from raes_contracts.runtime_state import RuntimeSnapshot


def temporal_pre_dispatch_assessments(
    request: ParticipantActionAdmissionRequest,
    snapshot: RuntimeSnapshot,
) -> list[ParticipantTemporalAssessmentModel]:
    """Identify already-impossible guarantees before native submission."""

    missed = []
    for context in request.temporal_contexts:
        scope = context.shared_time
        if scope is None:
            continue
        if scope.binding.temporal_kind == "deadline" and coordinate_key(scope.submitted_at) <= coordinate_key(
            scope.bound_end
        ):
            continue
        assessment = _assess_context(
            scope, request, snapshot, request.temporal_evidence, native_execution="not_dispatched"
        )
        if assessment.status != "met":
            missed.append(assessment)
    return missed


def temporal_guarantee_diagnostic(request: ParticipantActionAdmissionRequest) -> Diagnostic:
    return Diagnostic(
        code="runtime.participant-temporal-guarantee-unsatisfied",
        domain="participant",
        address=request.participant_address,
        message=(
            "The authored temporal guarantee is not satisfied; this does not imply native cancellation or rollback."
        ),
    )


def temporal_pre_dispatch_result(
    request: ParticipantActionAdmissionRequest,
    snapshot: RuntimeSnapshot,
) -> ParticipantActionApplyResult | None:
    """Record a rejected portable attempt without calling the native runtime."""

    assessments = temporal_pre_dispatch_assessments(request, snapshot)
    if not assessments:
        return None
    assessments = [
        _assess_context(
            context.shared_time, request, snapshot, request.temporal_evidence, native_execution="not_dispatched"
        )
        for context in request.temporal_contexts
        if context.shared_time is not None
    ]
    context = assessments[0].context
    action_result = ParticipantActionResultModel(
        status="rejected",
        participant_address=request.participant_address,
        episode_id=context.episode_id,
        action_instance_id=request.action_instance_id,
        action_contract_address=request.action_contract_address,
        observation_point=request.temporal_contexts[0].observation_point,
        preconditions=[
            {
                "precondition_id": f"shared-time:{assessment.context.binding.temporal_id}",
                "precondition_class": "temporal",
                "status": "unsatisfied" if assessment.status == "missed" else "unresolved",
                "participant_address": request.participant_address,
                "episode_id": context.episode_id,
                "action_contract_address": request.action_contract_address,
                "observation_point": request.temporal_contexts[0].observation_point,
                "support_refs": [assessment.context.binding.constraint_address],
                "diagnostics": [assessment.reason],
            }
            for assessment in assessments
            if assessment.status != "met"
        ],
        failure_class="precondition_unsatisfied",
        diagnostics=[assessment.reason for assessment in assessments],
    )
    events = list(
        participant_action_binding_events(
            replace(request, action_result=action_result, state_transition_kind="participant_temporal_rejected"),
            episode_id=context.episode_id,
            timestamp=datetime.now(UTC).isoformat(),
            post_state_digest=participant_binding_post_state_digest(request),
        )
    )
    events[0] = events[0].model_copy(update={"admission_disposition": ParticipantAdmissionDisposition.REJECTED})
    events[-1] = events[-1].model_copy(update={"temporal_assessments": assessments})
    histories = dict(snapshot.participant_behavior_history)
    histories[request.participant_address] = [
        *histories.get(request.participant_address, ()),
        *(participant_behavior_event_payload(event) for event in events),
    ]
    return ParticipantActionApplyResult(
        success=False,
        snapshot=snapshot.with_entries(dict(snapshot.entries), participant_behavior_history=histories),
        action_result=action_result,
        diagnostics=[temporal_guarantee_diagnostic(request)],
        changed_addresses=[request.participant_address],
    )


def assess_temporal_result(
    request: ParticipantActionAdmissionRequest,
    result: ParticipantActionApplyResult,
    authoritative: RuntimeSnapshot,
) -> ParticipantActionApplyResult:
    """Attach runtime-owned assessments without changing the native outcome."""

    contexts = [context.shared_time for context in request.temporal_contexts if context.shared_time is not None]
    if not contexts:
        return result
    assessments = []
    for context in contexts:
        evidence = (
            request.temporal_evidence
            if context.binding.temporal_kind == "dwell"
            else tuple(result.action_result.temporal_evidence)
        )
        assessments.append(_assess_context(context, request, authoritative, evidence, native_execution="reported"))
    histories = dict(result.snapshot.participant_behavior_history)
    history = list(histories[request.participant_address])
    terminal = ParticipantBehaviorHistoryEventModel.model_validate(history[-1])
    history[-1] = participant_behavior_event_payload(terminal.model_copy(update={"temporal_assessments": assessments}))
    histories[request.participant_address] = history
    satisfied = all(assessment.status == "met" for assessment in assessments)
    return cast(
        ParticipantActionApplyResult,
        replace(
            result,
            success=result.success and satisfied,
            snapshot=result.snapshot.with_entries(
                dict(result.snapshot.entries), participant_behavior_history=histories
            ),
            diagnostics=[*result.diagnostics, *(() if satisfied else (temporal_guarantee_diagnostic(request),))],
        ),
    )


def _assess_context(
    context: ParticipantTemporalExecutionContextModel,
    request: ParticipantActionAdmissionRequest,
    snapshot: RuntimeSnapshot,
    evidence: tuple[ParticipantTemporalEvidenceModel, ...],
    *,
    native_execution: Literal["not_dispatched", "reported"],
) -> ParticipantTemporalAssessmentModel:
    return assess_temporal_guarantee(
        context,
        evidence,
        request.observation_boundary_address,
        snapshot.time_model_state.clocks[context.binding.clock_address],
        native_execution=native_execution,
    )


def temporal_guarantees_met(request: ParticipantActionAdmissionRequest, result: ParticipantActionApplyResult) -> bool:
    """A failed or indeterminate guarantee never authorizes a native retry."""

    if not any(context.shared_time is not None for context in request.temporal_contexts):
        return True
    history = result.snapshot.participant_behavior_history.get(request.participant_address, ())
    assessments = history[-1].get("temporal_assessments", ()) if history else ()
    return bool(assessments) and all(item["status"] == "met" for item in assessments)

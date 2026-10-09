"""Cross-message checks for the stage reports of one mixed-backend invocation.

The validator joins stage reports to their installed binding, the shared
backend operation request and response transcript, and the trusted time-model
declaration resolved by the caller. It performs no I/O, dispatch or state
mutation, and passing it proves neither backend truth nor runtime adoption.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from ..canonical import canonical_json_digest
from ..operation_lifecycle import OperationState
from .backend_operation import (
    BackendOperationControlModel,
    BackendOperationRequestModel,
    OperationArtifactReferenceModel,
)
from .backend_operation_response import (
    BackendOperationAcknowledgementModel,
    BackendOperationMessage,
    BackendOperationOutcomeModel,
    BackendOperationProgressModel,
    BackendOperationReconciliationModel,
    BackendOperationResponseModel,
)
from .backend_operation_validation import backend_operation_request_digest, validate_backend_operation_history
from .mixed_backend_binding import (
    MixedBackendEdgeBindingModel,
    MixedBackendExecutionBindingModel,
    MixedBackendHandoffBindingModel,
    MixedBackendTimeRequirementModel,
)
from .mixed_backend_stages import (
    MIXED_BACKEND_STAGE_REPORT_CONTRACT_ID,
    MixedBackendDeliveryStageModel,
    MixedBackendExecutionStageModel,
    MixedBackendHandoffStageModel,
    MixedBackendObservationStageModel,
    MixedBackendStage,
    MixedBackendStageReportModel,
    MixedBackendTimeGrantStageModel,
)
from .mixed_backend_validation import require_mixed_backend_request
from .time_model import TimeModelDeclarationModel

_MAX_STAGE_REPORTS = 64
_UNSUPPORTED_ORDER = "time grant does not establish the required order within one segment"
_SubjectBinding = MixedBackendEdgeBindingModel | MixedBackendHandoffBindingModel
# Each stage may only follow its prerequisite; the stage after the time grant
# is the invocation itself and needs an ordered grant and accepted start.
_PREREQUISITES = {
    "edge": {"time-grant": None, "execution": "time-grant", "delivery": "execution", "observation": "delivery"},
    "handoff": {"time-grant": None, "handoff": "time-grant", "owner-readback": "handoff"},
}


@dataclass(frozen=True)
class _Transcript:
    """Facts the shared operation transcript establishes; never persisted authority."""

    accepted: bool
    outcome: BackendOperationOutcomeModel | None


def validate_mixed_backend_stage_reports(
    binding: MixedBackendExecutionBindingModel,
    request: BackendOperationRequestModel,
    responses: Sequence[BackendOperationResponseModel],
    reports: Sequence[MixedBackendStageReportModel],
    *,
    time_model: TimeModelDeclarationModel,
    controls: Sequence[BackendOperationControlModel] = (),
) -> None:
    """Validate one invocation's stage reports against its binding and shared transcript.

    ``time_model`` is the trusted declaration resolved from the binding's time
    requirement. Each stage must follow its prerequisite, and the invocation
    stage needs an ordered grant and an accepted acknowledgement, so nothing
    follows a refusal. A proposed shared outcome may claim success or known
    failure only when the stages establish it.
    """

    require_mixed_backend_request(binding, request)
    validate_backend_operation_history(request, responses, controls=controls)
    messages = [response.message for response in responses]
    accepted = any(
        isinstance(message, BackendOperationAcknowledgementModel) and message.disposition == "accepted"
        for message in messages
    )
    outcomes = [message for message in messages if isinstance(message, BackendOperationOutcomeModel)]
    transcript = _Transcript(accepted=accepted, outcome=outcomes[-1] if outcomes else None)
    subject = binding.subject
    seen: dict[str, MixedBackendStage] = {}
    for stage in _ordered_stages(request, reports):
        _require_prerequisite(subject, stage, seen, transcript)
        _require_stage_identity(subject, stage, seen, time_model)
        seen[stage.stage] = stage
    _require_honest_outcome(subject, seen, transcript)
    _require_cited_reports(messages, reports)


def _ordered_stages(
    request: BackendOperationRequestModel,
    reports: Sequence[MixedBackendStageReportModel],
) -> list[MixedBackendStage]:
    if len(reports) > _MAX_STAGE_REPORTS:
        raise ValueError("mixed stage report transcript exceeds its bound")
    digest = backend_operation_request_digest(request)
    by_sequence: dict[int, MixedBackendStageReportModel] = {}
    for report in reports:
        if report.binding != request.binding or report.request_digest != digest:
            raise ValueError("mixed stage report belongs to another invocation")
        if by_sequence.setdefault(report.sequence, report) != report:
            raise ValueError("duplicate stage report sequence changed its content")
    stages = [by_sequence[sequence].stage for sequence in sorted(by_sequence)]
    if len({stage.stage for stage in stages}) != len(stages):
        raise ValueError("an invocation reports each stage at most once")
    return stages


def _require_prerequisite(
    subject: _SubjectBinding,
    stage: MixedBackendStage,
    seen: dict[str, MixedBackendStage],
    transcript: _Transcript,
) -> None:
    prerequisites = _PREREQUISITES[subject.kind]
    if stage.stage not in prerequisites:
        raise ValueError("stage does not belong to this mixed binding obligation")
    prerequisite = prerequisites[stage.stage]
    if prerequisite is not None and prerequisite not in seen:
        raise ValueError("mixed stage report precedes its prerequisite stage")
    if prerequisite == "time-grant" and (not transcript.accepted or seen[prerequisite].comparison != "ordered"):
        raise ValueError("invocation requires an ordered time grant and an accepted acknowledgement")
    if stage.stage == "delivery" and seen["execution"].status == "failed":
        raise ValueError("known execution failure cannot be followed by delivery")


def _require_stage_identity(
    subject: _SubjectBinding,
    stage: MixedBackendStage,
    seen: dict[str, MixedBackendStage],
    time_model: TimeModelDeclarationModel,
) -> None:
    # An owner readback naming neither admitted owner is a valid contradictory
    # fact; the outcome rules keep such a transfer indeterminate.
    if isinstance(stage, MixedBackendTimeGrantStageModel):
        _require_time_grant(subject, stage, time_model)
    elif isinstance(stage, MixedBackendExecutionStageModel):
        _require_execution(subject, stage)
    elif isinstance(stage, MixedBackendDeliveryStageModel):
        _require_delivery(subject, stage)
    elif isinstance(stage, MixedBackendObservationStageModel):
        _require_observation(subject, stage)
    elif isinstance(stage, MixedBackendHandoffStageModel):
        _require_handoff(subject, stage, seen["time-grant"])


def _require_time_grant(
    subject: _SubjectBinding,
    grant: MixedBackendTimeGrantStageModel,
    time_model: TimeModelDeclarationModel,
) -> None:
    required = subject.time
    if (grant.mapping_ref, grant.ordering_basis) != (required.mapping_ref, required.ordering_basis):
        raise ValueError("time grant differs from the bound mapping or ordering basis")
    if not set(subject.required_evidence_refs) <= {*grant.mapping_evidence_refs, *grant.timing_evidence_refs}:
        raise ValueError("time grant does not cite the admitted evidence obligations")
    if grant.comparison == "ordered":
        _require_mapped_order(required, grant, time_model)


def _require_mapped_order(
    required: MixedBackendTimeRequirementModel,
    grant: MixedBackendTimeGrantStageModel,
    time_model: TimeModelDeclarationModel,
) -> None:
    mapping = time_model.mappings.get(required.mapping_ref)
    source, destination = grant.source_coordinate, grant.destination_coordinate
    if mapping is None or source.segment != destination.segment:
        raise ValueError(_UNSUPPORTED_ORDER)
    mapped = Fraction(source.tick * mapping.scale.numerator, mapping.scale.denominator) + mapping.offset_ticks
    if (mapped, source.microstep) > (destination.tick, destination.microstep):
        raise ValueError(_UNSUPPORTED_ORDER)


def _require_execution(subject: MixedBackendEdgeBindingModel, execution: MixedBackendExecutionStageModel) -> None:
    observed = (
        execution.bridge,
        execution.source_action_address,
        execution.destination_action_address,
        frozenset(execution.mapping_loss_refs),
    )
    expected = (
        subject.bridge,
        subject.source_action_address,
        subject.destination_action_address,
        frozenset({subject.mapping_loss.limitation_ref}),
    )
    if observed != expected:
        raise ValueError("execution report differs from the installed bridge, subjects or declared loss")


def _require_delivery(subject: MixedBackendEdgeBindingModel, delivery: MixedBackendDeliveryStageModel) -> None:
    if delivery.destination_component_id != subject.owner_component_id:
        raise ValueError("delivery receipt differs from the destination provider")


def _require_observation(
    subject: MixedBackendEdgeBindingModel,
    observation: MixedBackendObservationStageModel,
) -> None:
    observed = (observation.participant_address, observation.audience_scope_ref)
    if subject.observation_reader is None or observed != (subject.participant_address, subject.audience_scope_ref):
        raise ValueError("participant observation differs from the bound reader, participant or audience")


def _require_handoff(
    subject: MixedBackendHandoffBindingModel,
    handoff: MixedBackendHandoffStageModel,
    grant: MixedBackendTimeGrantStageModel,
) -> None:
    if handoff.order_ref != grant.order_ref:
        raise ValueError("native handoff differs from its granted order")
    if not set(subject.required_evidence_refs) <= set(handoff.evidence_refs):
        raise ValueError("native handoff does not cite the admitted evidence obligations")


def _require_honest_outcome(
    subject: _SubjectBinding,
    seen: dict[str, MixedBackendStage],
    transcript: _Transcript,
) -> None:
    outcome = transcript.outcome
    if outcome is None or outcome.proposed_state not in {OperationState.SUCCEEDED, OperationState.FAILED}:
        return
    established = _edge_state(seen) if subject.kind == "edge" else _handoff_state(subject, seen)
    if outcome.proposed_state != established:
        raise ValueError("shared outcome claims more than the mixed stages establish")


def _require_cited_reports(
    messages: Sequence[BackendOperationMessage],
    reports: Sequence[MixedBackendStageReportModel],
) -> None:
    cited = {
        reference.digest
        for message in messages
        for reference in _evidence_references(message)
        if reference.contract_id == MIXED_BACKEND_STAGE_REPORT_CONTRACT_ID
    }
    supplied = {canonical_json_digest(report.model_dump(mode="json")) for report in reports}
    if not cited <= supplied:
        raise ValueError("shared operation evidence cites a stage report that this invocation did not supply")


def _evidence_references(message: BackendOperationMessage) -> tuple[OperationArtifactReferenceModel, ...]:
    if isinstance(message, BackendOperationProgressModel):
        return message.evidence_refs
    if isinstance(message, (BackendOperationOutcomeModel, BackendOperationReconciliationModel)):
        return message.effects.evidence_refs
    return ()


def _edge_state(seen: dict[str, MixedBackendStage]) -> OperationState:
    execution = seen.get("execution")
    if execution is None or execution.status in {"partial", "unknown"}:
        return OperationState.INDETERMINATE
    if execution.status == "failed":
        return OperationState.FAILED
    return OperationState.SUCCEEDED if "delivery" in seen else OperationState.INDETERMINATE


def _handoff_state(subject: MixedBackendHandoffBindingModel, seen: dict[str, MixedBackendStage]) -> OperationState:
    # Only a committed transfer read back at the destination owner and next phase
    # revision succeeds; only a failed or stale one that kept the source owner fails.
    handoff, readback = seen.get("handoff"), seen.get("owner-readback")
    state = OperationState.INDETERMINATE
    if handoff is not None and readback is not None:
        owner = (readback.owner_component_id, readback.owner_ref, readback.phase_revision)
        destination = (subject.destination_component_id, subject.destination_owner_ref, handoff.phase_revision + 1)
        source = (subject.source_component_id, subject.source_owner_ref, handoff.phase_revision)
        if handoff.status == "committed" and owner == destination:
            state = OperationState.SUCCEEDED
        elif handoff.status in {"failed", "stale"} and owner == source:
            state = OperationState.FAILED
    return state


__all__ = ["validate_mixed_backend_stage_reports"]

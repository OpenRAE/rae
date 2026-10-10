"""Cross-message checks for the stage reports of one mixed-backend invocation.

The validator joins stage reports to their installed binding, the shared
backend operation request and response transcript, and trusted inputs resolved
by the caller: the time-model declaration with the reference and digest it was
resolved under, the committed time readback the coordinator received, RAES's
own time readback after the invocation and, for a native handoff, the committed
composition state. It performs no I/O, dispatch or state mutation, and passing
it proves neither backend truth nor runtime adoption.
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
    MixedBackendServiceModel,
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
from .mixed_runtime import MixedCompositionRuntimeStateModel
from .time_model import (
    TimeCoordinateModel,
    TimeModelDeclarationModel,
    TimeRuntimeStateModel,
    validate_time_runtime_state,
)

_MAX_STAGE_REPORTS = 64
_UNSUPPORTED_ORDER = "time grant does not establish the required order within one segment"
_SubjectBinding = MixedBackendEdgeBindingModel | MixedBackendHandoffBindingModel
# Each stage may only follow its prerequisite; the stage after the time grant
# is the invocation itself and needs an ordered grant and accepted start.
_PREREQUISITES = {
    "edge": {"time-grant": None, "execution": "time-grant", "delivery": "execution", "observation": "delivery"},
    "handoff": {"time-grant": None, "handoff": "time-grant", "owner-readback": "handoff"},
}
# A report's sequence is its stage's fixed position in that chain, so producers
# that see neither each other's reports nor a shared counter can number them.
_STAGE_SEQUENCE = {"time-grant": 1, "execution": 2, "handoff": 2, "delivery": 3, "owner-readback": 3, "observation": 4}


@dataclass(frozen=True)
class _Transcript:
    """Facts the shared operation transcript establishes; never persisted authority."""

    accepted: bool
    outcome: BackendOperationOutcomeModel | None


@dataclass(frozen=True)
class MixedBackendStageContext:
    """Trusted, caller-resolved inputs for one invocation's stage reports; none comes from a backend.

    ``time_model`` is the declaration that the caller resolved under
    ``time_model_ref`` and ``time_model_digest``, which must equal the binding's
    time requirement. ``time_state`` is the committed time readback that the
    coordinator received. ``post_time_state`` is RAES's own time readback after
    the invocation, or ``None`` when none was taken. ``composition_state`` is
    the committed composition state of the binding's profile: it must activate
    a bound edge, or hold a handoff's source component but not its destination.
    A native handoff requires it.
    """

    time_model: TimeModelDeclarationModel
    time_model_ref: str
    time_model_digest: str
    time_state: TimeRuntimeStateModel
    post_time_state: TimeRuntimeStateModel | None = None
    composition_state: MixedCompositionRuntimeStateModel | None = None


@dataclass(frozen=True)
class _Trusted:
    """Facts derived from the trusted context that the reports must match."""

    time_model: TimeModelDeclarationModel
    coordinates: tuple[TimeCoordinateModel, TimeCoordinateModel]
    time_confirmed: bool
    fence: tuple[str, int] | None


def validate_mixed_backend_stage_reports(
    binding: MixedBackendExecutionBindingModel,
    request: BackendOperationRequestModel,
    responses: Sequence[BackendOperationResponseModel],
    reports: Sequence[MixedBackendStageReportModel],
    *,
    context: MixedBackendStageContext,
    controls: Sequence[BackendOperationControlModel] = (),
) -> None:
    """Validate one invocation's stage reports against its binding, transcript and trusted context.

    The trusted time model must be resolved under the binding's time-model
    reference and digest, and a committed composition state must still
    activate the bound edge or precede the bound handoff. The grant's
    coordinates must equal the committed time readback, and a native handoff
    must name the committed composition history head and phase revision. Each
    report's ``sequence`` must be its stage's fixed chain position (time grant
    1, execution or handoff 2, delivery or owner readback 3, observation 4),
    and reports are accepted in ascending ``sequence`` whatever order they are
    supplied in. Each stage must follow its prerequisite and name the service
    pinned for its role, and the invocation stage needs an ordered grant and an
    accepted acknowledgement. A proposed success or known failure must equal
    the state that the stages and the trusted readbacks establish.
    """

    require_mixed_backend_request(binding, request)
    validate_backend_operation_history(request, responses, controls=controls)
    trusted = _trusted_inputs(binding, context)
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
        _require_producer(subject, stage)
        _require_stage_identity(subject, stage, seen, trusted)
        seen[stage.stage] = stage
    _require_honest_outcome(subject, seen, transcript, trusted)
    _require_cited_reports(messages, reports)


def _trusted_inputs(binding: MixedBackendExecutionBindingModel, context: MixedBackendStageContext) -> _Trusted:
    required, time_model = binding.subject.time, context.time_model
    if (context.time_model_ref, context.time_model_digest) != (required.time_model_ref, required.time_model_digest):
        raise ValueError("trusted time model differs from the binding's time model reference or digest")
    validate_time_runtime_state(time_model, context.time_state)
    before = _bound_coordinates(required, context.time_state)
    confirmed = _time_confirmed(required, time_model, before, context.post_time_state)
    return _Trusted(time_model, before, confirmed, _composition_fence(binding, context.composition_state))


def _bound_coordinates(
    required: MixedBackendTimeRequirementModel,
    state: TimeRuntimeStateModel,
) -> tuple[TimeCoordinateModel, TimeCoordinateModel]:
    source = state.clocks.get(required.source_clock_address)
    destination = state.clocks.get(required.destination_clock_address)
    if source is None or destination is None:
        raise ValueError("time readback does not cover the bound clocks")
    return source.coordinate, destination.coordinate


def _time_confirmed(
    required: MixedBackendTimeRequirementModel,
    time_model: TimeModelDeclarationModel,
    before: tuple[TimeCoordinateModel, TimeCoordinateModel],
    post_time_state: TimeRuntimeStateModel | None,
) -> bool:
    # RAES's own post-invocation readback confirms time only when it matches the
    # declaration and neither bound clock moved backwards.
    if post_time_state is None:
        return False
    validate_time_runtime_state(time_model, post_time_state)
    after = _bound_coordinates(required, post_time_state)
    return all(_position(late) >= _position(early) for early, late in zip(before, after, strict=True))


def _position(coordinate: TimeCoordinateModel) -> tuple[int, int, int]:
    return coordinate.segment, coordinate.tick, coordinate.microstep


def _composition_fence(
    binding: MixedBackendExecutionBindingModel,
    state: MixedCompositionRuntimeStateModel | None,
) -> tuple[str, int] | None:
    if state is None:
        if binding.subject.kind == "handoff":
            raise ValueError("native handoff validation requires the committed composition state")
        return None
    if (state.profile_id, state.profile_digest) != (binding.profile_id, binding.profile_digest):
        raise ValueError("committed composition state belongs to another profile")
    _require_open_obligation(binding.subject, state)
    return state.history_head, state.phase_revision


def _require_open_obligation(subject: _SubjectBinding, state: MixedCompositionRuntimeStateModel) -> None:
    # The committed state must still be the one the obligation acts on: the
    # edge is active, or the handoff's source is active and its destination not.
    if isinstance(subject, MixedBackendEdgeBindingModel):
        if subject.edge_id not in state.active_edge_ids:
            raise ValueError("committed composition state does not activate the bound edge")
        return
    active = set(state.active_component_ids)
    if subject.source_component_id not in active or subject.destination_component_id in active:
        raise ValueError("committed composition state does not precede the native handoff")


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
        if report.sequence != _STAGE_SEQUENCE[report.stage.stage]:
            raise ValueError("stage report sequence differs from its stage's chain position")
        # One number per stage kind, so a second report of a stage is either a
        # retransmission or a contradiction.
        if by_sequence.setdefault(report.sequence, report) != report:
            raise ValueError("duplicate stage report sequence changed its content")
    return [by_sequence[sequence].stage for sequence in sorted(by_sequence)]


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


def _require_producer(subject: _SubjectBinding, stage: MixedBackendStage) -> None:
    if stage.producer != _pinned_producer(subject, stage.stage):
        raise ValueError("stage report names a producer other than the service pinned for its stage")


def _pinned_producer(subject: _SubjectBinding, stage_kind: str) -> MixedBackendServiceModel | None:
    if stage_kind == "time-grant":
        return subject.time.coordinator
    if isinstance(subject, MixedBackendEdgeBindingModel):
        services = {
            "execution": subject.bridge,
            "delivery": subject.delivery_reader,
            "observation": subject.observation_reader,
        }
    else:
        services = {"handoff": subject.transfer, "owner-readback": subject.owner_reader}
    return services[stage_kind]


def _require_stage_identity(
    subject: _SubjectBinding,
    stage: MixedBackendStage,
    seen: dict[str, MixedBackendStage],
    trusted: _Trusted,
) -> None:
    # An owner readback naming neither admitted owner is a valid contradictory
    # fact; the outcome rules keep such a transfer indeterminate.
    if isinstance(stage, MixedBackendTimeGrantStageModel):
        _require_time_grant(subject, stage, trusted)
    elif isinstance(stage, MixedBackendExecutionStageModel):
        _require_execution(subject, stage)
    elif isinstance(stage, MixedBackendDeliveryStageModel):
        _require_delivery(subject, stage)
    elif isinstance(stage, MixedBackendObservationStageModel):
        _require_observation(subject, stage)
    elif isinstance(stage, MixedBackendHandoffStageModel):
        _require_handoff(subject, stage, seen["time-grant"], trusted)


def _require_time_grant(subject: _SubjectBinding, grant: MixedBackendTimeGrantStageModel, trusted: _Trusted) -> None:
    required = subject.time
    if (grant.mapping_ref, grant.ordering_basis) != (required.mapping_ref, required.ordering_basis):
        raise ValueError("time grant differs from the bound mapping or ordering basis")
    if (grant.source_coordinate, grant.destination_coordinate) != trusted.coordinates:
        raise ValueError("time grant coordinates differ from the committed time readback")
    if not set(subject.required_evidence_refs) <= {*grant.mapping_evidence_refs, *grant.timing_evidence_refs}:
        raise ValueError("time grant does not cite the admitted evidence obligations")
    if grant.comparison == "ordered":
        _require_mapped_order(required, grant, trusted.time_model)


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
        execution.source_action_address,
        execution.destination_action_address,
        frozenset(execution.mapping_loss_refs),
    )
    expected = (
        subject.source_action_address,
        subject.destination_action_address,
        frozenset({subject.mapping_loss.limitation_ref}),
    )
    if observed != expected:
        raise ValueError("execution report differs from the installed subjects or declared loss")


def _require_delivery(subject: MixedBackendEdgeBindingModel, delivery: MixedBackendDeliveryStageModel) -> None:
    if delivery.destination_component_id != subject.owner_component_id:
        raise ValueError("delivery receipt differs from the destination provider")


def _require_observation(
    subject: MixedBackendEdgeBindingModel,
    observation: MixedBackendObservationStageModel,
) -> None:
    observed = (observation.participant_address, observation.audience_scope_ref)
    if observed != (subject.participant_address, subject.audience_scope_ref):
        raise ValueError("participant observation differs from the bound participant or audience")


def _require_handoff(
    subject: MixedBackendHandoffBindingModel,
    handoff: MixedBackendHandoffStageModel,
    grant: MixedBackendTimeGrantStageModel,
    trusted: _Trusted,
) -> None:
    if handoff.order_ref != grant.order_ref:
        raise ValueError("native handoff differs from its granted order")
    if (handoff.predecessor_history_head, handoff.phase_revision) != trusted.fence:
        raise ValueError("native handoff differs from the committed composition history head or phase revision")
    if not set(subject.required_evidence_refs) <= set(handoff.evidence_refs):
        raise ValueError("native handoff does not cite the admitted evidence obligations")


def _require_honest_outcome(
    subject: _SubjectBinding,
    seen: dict[str, MixedBackendStage],
    transcript: _Transcript,
    trusted: _Trusted,
) -> None:
    outcome = transcript.outcome
    if outcome is None or outcome.proposed_state not in {OperationState.SUCCEEDED, OperationState.FAILED}:
        return
    established = _edge_state(seen, trusted) if subject.kind == "edge" else _handoff_state(subject, seen, trusted)
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


def _refused_grant_state(seen: dict[str, MixedBackendStage]) -> OperationState:
    # Only an explicit incomparable grant proves that no invocation could start.
    grant = seen.get("time-grant")
    refused = grant is not None and grant.comparison == "incomparable"
    return OperationState.FAILED if refused else OperationState.INDETERMINATE


def _edge_state(seen: dict[str, MixedBackendStage], trusted: _Trusted) -> OperationState:
    execution = seen.get("execution")
    if execution is None:
        return _refused_grant_state(seen)
    if execution.status == "failed":
        return OperationState.FAILED
    delivered = execution.status == "succeeded" and "delivery" in seen
    return OperationState.SUCCEEDED if delivered and trusted.time_confirmed else OperationState.INDETERMINATE


def _handoff_state(
    subject: MixedBackendHandoffBindingModel,
    seen: dict[str, MixedBackendStage],
    trusted: _Trusted,
) -> OperationState:
    # Only a committed transfer read back at the destination owner and next phase
    # revision succeeds; only a failed or stale one that kept the source owner
    # fails. Both need confirmed post-transfer time.
    handoff, readback = seen.get("handoff"), seen.get("owner-readback")
    if handoff is None:
        return _refused_grant_state(seen)
    state = OperationState.INDETERMINATE
    if readback is not None and trusted.time_confirmed:
        # ``_require_handoff`` fenced this revision on the committed composition state.
        revision = handoff.phase_revision
        owner = (readback.owner_component_id, readback.owner_ref, readback.phase_revision)
        destination = (subject.destination_component_id, subject.destination_owner_ref, revision + 1)
        source = (subject.source_component_id, subject.source_owner_ref, revision)
        if handoff.status == "committed" and owner == destination:
            state = OperationState.SUCCEEDED
        elif handoff.status in {"failed", "stale"} and owner == source:
            state = OperationState.FAILED
    return state


__all__ = ["MixedBackendStageContext", "validate_mixed_backend_stage_reports"]

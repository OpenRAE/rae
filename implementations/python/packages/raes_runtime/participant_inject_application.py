"""Participant composition through the incumbent crossing transaction owner."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from raes_contracts.associated_artifacts import require_instantiated_scenario_reference
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.inject_occurrence_outcome import InjectOccurrenceCorrelationModel
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingInteractionKind,
    ParticipantCrossingSubjectKind,
)
from raes_contracts.contracts.participant_inject_application import (
    ParticipantInjectApplicationModel,
    ParticipantInjectContentModel,
    ParticipantInjectDeliveryReceiptModel,
)
from raes_contracts.runtime_state import OperationKind, OperationState
from raes_processor.models import ParticipantInjectDeliveryRuntime

from .control_plane_mutation import control_plane_mutation
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from .inject_capture import InjectCaptureResult
from .participant_control_runtime import ParticipantControlLiveCut
from .participant_crossing_egress import ParticipantViewSerialization, serialize_participant_view
from .participant_inject_delivery import ParticipantInjectResolution

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_control_effects import ControlInjectEffectModel
    from raes_contracts.contracts.participant_control_occurrence_v2 import ParticipantControlOccurrenceV2Model

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord
    from .participant_crossing_mediation import PreparedParticipantCrossing


def deliver_participant_inject(
    plane: RuntimeControlPlane, application: object, *, identity: object | None = None
) -> ParticipantInjectDeliveryReceiptModel:
    if plane._inject_delivery is None:
        raise ValueError("participant inject delivery is unavailable")
    if not isinstance(application, ParticipantInjectApplicationModel):
        raise TypeError("inject delivery requires a typed application")
    application = ParticipantInjectApplicationModel.model_validate(application.model_dump(mode="json"))
    delivery = _authorized_binding(plane, application, identity)
    with control_plane_mutation(plane, OperationKind.PARTICIPANT_CROSSING):
        plane._reload_derived_state()
        context = operation_admission_context(
            plane, kind=OperationKind.PARTICIPANT_CROSSING, request=application, identity=identity
        )
        existing = plane._store.find_by_idempotency(application.request_key, context=context)
        if existing is not None:
            if (
                existing.inject_delivery is None
                or existing.inject_delivery.application != application
                or not plane._operation_read_allowed(existing, identity)
            ):
                raise ValueError("inject delivery retry conflicts")
            if existing.status.state is not OperationState.SUCCEEDED:
                raise ValueError("inject delivery remains withheld")
            return ParticipantInjectDeliveryReceiptModel(
                operation_id=existing.receipt.operation_id, delivery=deepcopy(existing.inject_delivery)
            )
        content = _deliver(plane, application, delivery, identity)
        committed = plane._store.find_by_idempotency(application.request_key, context=context)
        return ParticipantInjectDeliveryReceiptModel(operation_id=committed.receipt.operation_id, delivery=content)


def _authorized_binding(
    plane: RuntimeControlPlane, application: ParticipantInjectApplicationModel, identity: object | None
) -> ParticipantInjectDeliveryRuntime:
    if (
        not isinstance(identity, ControlPlaneIdentity)
        or identity.target_name != plane.target_name
        or identity.roles.isdisjoint({ControlPlaneRole.OPERATOR, ControlPlaneRole.BACKEND})
    ):
        raise PermissionError("inject delivery authority is unavailable")
    delivery = plane._inject_delivery.model.participant_inject_deliveries.get(application.delivery_address)
    if (
        delivery is None
        or delivery.participant_address != application.participant_address
        or canonical_json_digest(delivery.spec) != application.delivery_digest
    ):
        raise ValueError("inject delivery binding differs")
    specification = plane._behavior_specifications.get(delivery.behavior_specification_address)
    if specification is None or application.delivery_address not in specification.participant_inject_delivery_addresses:
        raise ValueError("inject delivery behavior specification is not installed")
    _require_audience(identity, delivery)
    return delivery


def _require_audience(identity: ControlPlaneIdentity, delivery: ParticipantInjectDeliveryRuntime) -> None:
    if not any(
        binding.participant_address == delivery.participant_address
        and binding.audience_scope_ref == delivery.audience_scope_ref
        for binding in identity.participant_audience_subjects
    ):
        raise PermissionError("inject delivery audience is unavailable")


def _require_cut(
    plane: RuntimeControlPlane,
    application: ParticipantInjectApplicationModel,
    delivery: ParticipantInjectDeliveryRuntime,
) -> None:
    if plane._snapshot_state.revision != application.expected_snapshot_revision:
        raise ValueError("inject delivery snapshot is stale")
    state = plane._snapshot.participant_episode_results.get(application.participant_address, {})
    if (state.get("episode_id"), state.get("status")) != (application.episode_id, "running"):
        raise ValueError("inject delivery episode is not running")
    from .participant_inject_temporal import require_delivery_time

    require_delivery_time(plane._inject_delivery.model, delivery, plane._snapshot)


def require_projected_inject(
    application: ParticipantInjectApplicationModel,
    delivery: ParticipantInjectDeliveryRuntime,
    content: ParticipantInjectContentModel,
    correlation: InjectOccurrenceCorrelationModel,
) -> ParticipantInjectContentModel:
    try:
        content = ParticipantInjectContentModel.model_validate(content.model_dump(mode="json"))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("inject delivery projection is invalid") from None
    if (
        content.application != application
        or content.correlation != correlation
        or content.visibility_projection_ref != delivery.disclosure_basis_ref
        or content.disclosed_item.artifact_id != delivery.result_item_address
        or content.observation_boundary_ref != delivery.observation_boundary_address
    ):
        raise ValueError("inject delivery projection binding differs")
    return content


def _deliver(
    plane: RuntimeControlPlane,
    application: ParticipantInjectApplicationModel,
    delivery: ParticipantInjectDeliveryRuntime,
    identity: ControlPlaneIdentity,
) -> ParticipantInjectContentModel:
    _require_cut(plane, application, delivery)
    correlation = _world_correlation(plane, application, delivery, identity)
    resolution = _resolve_delivery(plane, application, delivery, correlation)
    content = require_projected_inject(application, delivery, resolution.content, correlation)
    cut = _projection_cut(resolution)
    if resolution.evidence.audience_scope_ref != delivery.audience_scope_ref:
        raise ValueError("inject delivery projection binding differs")
    if cut.request_ref != application.request_key or not set(delivery.evidence_requirement_addresses) <= set(
        resolution.evidence.required_evidence_refs
    ):
        raise ValueError("inject delivery result or evidence binding differs")
    from .participant_inject_control import require_delivery_control

    require_delivery_control(plane, application, delivery, cut.effective_order, identity)
    # The egress owner commits the exact projected carrier and single-use join
    # before returning it to the authenticated audience.
    return serialize_participant_view(
        plane,
        content,
        ParticipantViewSerialization(
            participant_address=application.participant_address,
            episode_id=application.episode_id,
            subject_kind=ParticipantCrossingSubjectKind.PARTICIPANT_INJECT_DELIVERY,
            interaction_kind=ParticipantCrossingInteractionKind.PARTICIPANT_INJECT_DELIVERY,
            projection_ref=content.visibility_projection_ref,
            identity=identity,
            crossing_evidence=resolution.evidence,
            idempotency_key=application.request_key,
            inject_application=application,
            effective_order=cut.effective_order,
        ),
    )


def retained_delivery_control(
    plane: RuntimeControlPlane, application: ParticipantInjectApplicationModel | None
) -> ParticipantControlOccurrenceV2Model | None:
    if application is None or application.control is None:
        return None
    from raes_contracts.contracts.participant_control_occurrence_v2 import ParticipantControlOccurrenceV2Model

    return next(
        ParticipantControlOccurrenceV2Model.model_validate(item)
        for item in plane._snapshot.participant_control_history[application.participant_address]
        if item["event_id"] == application.control.event_id
    )


def revalidate_delivery_egress(
    plane: RuntimeControlPlane,
    serialization: ParticipantViewSerialization,
    prepared: PreparedParticipantCrossing,
    governed: ParticipantInjectContentModel,
    correlation: InjectOccurrenceCorrelationModel,
) -> ParticipantInjectContentModel:
    from .participant_inject_control import require_delivery_control

    application = serialization.inject_application
    delivery = _authorized_binding(plane, application, serialization.identity)
    _require_cut(plane, application, delivery)
    require_delivery_control(plane, application, delivery, prepared.intent.effective_order, serialization.identity)
    return require_projected_inject(application, delivery, governed, correlation)


def submit_inject_effect(
    control_plane: RuntimeControlPlane,
    application: ParticipantInjectApplicationModel,
    target: ControlInjectEffectModel,
    principal: ControlPlaneIdentity,
    idempotency_key: str,
) -> None:
    if control_plane._inject_delivery is None:
        raise ValueError("inject effect delivery owner is unavailable")
    delivery = control_plane._inject_delivery.model.participant_inject_deliveries.get(application.delivery_address)
    if (
        delivery is None
        or delivery.source_item_address == delivery.result_item_address
        or (
            delivery.inject_address,
            delivery.event_address,
            delivery.script_address,
            delivery.story_address,
            delivery.source_item_address,
            delivery.result_item_address,
            delivery.disclosure_basis_ref,
        )
        != (
            target.inject_ref,
            target.event_ref,
            target.script_ref,
            target.story_ref,
            target.source_item_ref,
            target.result_item_ref,
            target.disclosure_ref.ref,
        )
    ):
        raise ValueError("inject effect requires its exact fresh-result owner coordinates")
    control_plane.deliver_participant_inject(
        application.model_copy(update={"request_key": idempotency_key}),
        identity=principal,
    )


def _world_correlation(
    plane: RuntimeControlPlane,
    application: ParticipantInjectApplicationModel,
    delivery: ParticipantInjectDeliveryRuntime,
    identity: ControlPlaneIdentity,
) -> InjectOccurrenceCorrelationModel:
    world = plane._read_inject_record(application.world_operation_id, identity)
    correlation = plane.get_inject_correlation(application.world_operation_id, identity=identity)
    if world is None or correlation is None:
        raise ValueError("inject delivery world predecessor is unavailable")
    require_instantiated_scenario_reference(
        plane._inject_delivery.model.realization_instance, world.inject_occurrence.scenario
    )
    placement = world.inject_occurrence.request.placement
    if (
        world.inject_occurrence.request.inject != delivery.inject_address
        or placement.kind != "schedule"
        or (placement.event, placement.script, placement.story)
        != (delivery.event_address, delivery.script_address, delivery.story_address)
    ):
        raise ValueError("inject delivery occurrence anchor differs")
    _require_capture(plane, world)
    return correlation


def _require_capture(plane: RuntimeControlPlane, world: ControlPlaneOperationRecord) -> None:
    capture = world.result_payload
    if any(demand.required for demand in plane._inject_delivery.model.observation_demands) and (
        capture is None or InjectCaptureResult.model_validate(capture).status != "succeeded"
    ):
        raise ValueError("inject delivery evidence capture is unavailable")


def _resolve_delivery(
    plane: RuntimeControlPlane,
    application: ParticipantInjectApplicationModel,
    delivery: ParticipantInjectDeliveryRuntime,
    correlation: InjectOccurrenceCorrelationModel,
) -> ParticipantInjectResolution:
    try:
        with plane._mutation_authority.external_call():
            resolution = plane._execution_adapter.call(
                "control",
                plane._inject_delivery.resolver.resolve_delivery,
                deepcopy(delivery),
                application,
                correlation,
                deepcopy(plane._snapshot),
                timeout_ms=plane._supervision.admission_ms,
            )
    except Exception:
        raise ValueError("inject delivery projection is unavailable") from None
    plane._reload_derived_state()
    _require_cut(plane, application, delivery)
    if not isinstance(resolution, ParticipantInjectResolution):
        raise ValueError("inject delivery projection is unavailable")
    return resolution


def _projection_cut(resolution: ParticipantInjectResolution) -> ParticipantControlLiveCut:
    try:
        return ParticipantControlLiveCut.model_validate(resolution.cut.model_dump(mode="json"))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("inject delivery order cut is unavailable") from None


def require_delivery_policy_pin(
    plane: RuntimeControlPlane, serialization: ParticipantViewSerialization, prepared: PreparedParticipantCrossing
) -> None:
    if serialization.inject_application is None or prepared.decision is None:
        return
    delivery = plane._inject_delivery.model.participant_inject_deliveries[
        serialization.inject_application.delivery_address
    ]
    policy = prepared.decision.occurrence.policy
    if (policy.policy_id, policy.policy_revision) != (delivery.policy_ref, delivery.policy_revision):
        raise ValueError("inject delivery policy pin differs")

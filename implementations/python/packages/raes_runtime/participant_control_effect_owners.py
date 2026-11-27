"""Closed joins to real inject and evidenced cancellation operations."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from raes_contracts.contracts import InjectTriggerRequestModel
from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model
from raes_contracts.contracts.participant_control_effects import ControlInjectEffectModel
from raes_contracts.errors import ConflictError
from raes_contracts.runtime_state import OperationState

from .participant_control_intents import ParticipantCancellationControlIntent
from .participant_control_receipts import owner_idempotency_key

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_control_coordinates import ParticipantControlContextModel
    from raes_contracts.contracts.participant_control_effects import ControlEffectRequestModel, ControlEffectTarget
    from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
    from raes_contracts.contracts.participant_control_results import ControlRealizationBindingModel

    from .control_plane import RuntimeControlPlane
    from .control_plane_security import ControlPlaneIdentity
    from .control_plane_store import ControlPlaneOperationRecord
    from .participant_control_binding import ParticipantControlRuntimeBinding
    from .participant_control_effects import ParticipantControlEffectOperation


def prepare_v2_effect_dispatch(
    plane: RuntimeControlPlane,
    binding: ParticipantControlRuntimeBinding,
    evaluation: ParticipantControlEvaluationV2Model,
    origin: ControlPlaneOperationRecord,
    request: ControlEffectRequestV2Model,
) -> tuple[ControlRealizationBindingModel, ControlPlaneOperationRecord | None] | None:
    """Observe finished work; require current permission before any owner call."""
    from raes_contracts.contracts.participant_control_continuation import (
        validate_participant_control_effect_dispatch_v2,
    )

    from .participant_control_binding import control_context_admits, resolve_control_context
    from .participant_control_evaluation_v2 import _EvaluationCut
    from .participant_control_receipts import claim_outcome, realization, retained_effect_claim

    claim = retained_effect_claim(plane, origin, request)
    if claim is not None:
        disposition = claim_outcome(plane, claim, request)
        if disposition in {"applied", "failed"}:
            return realization(request, disposition, claim.receipt.operation_id), claim
    cut = _EvaluationCut.capture(plane, origin=origin)
    # The resolver context carries installed owner and support callbacks. Each boundary logs its own failure.
    context = resolve_control_context(lambda: cut.call(binding.resolver.validation_context, evaluation))
    if context is None or not control_context_admits(
        lambda: cut.call(lambda: validate_participant_control_effect_dispatch_v2(evaluation, request, context))
    ):
        return realization(request, "withheld", "authority-unresolved." + request.effect_id), None
    return None


def resume_owned_effect(
    plane: RuntimeControlPlane,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
) -> None:
    """Cancellation delivery resumes only through its incumbent one-use ledger."""
    from .participant_control_receipts import origin_principal, owner_record

    if not isinstance(request, ControlEffectRequestV2Model) or request.target.kind != "interrupt":
        return
    owner = owner_record(plane, claim, request)
    if owner is not None and owner.status.state is OperationState.SUCCEEDED:
        participant = owner.result_payload["participant_control_cancellation"]["participant_address"]
        plane.dispatch_participant_cancellation(
            owner.receipt.operation_id, identity=origin_principal(plane, claim, participant)
        )


def binds_owned_effect(
    operation: ParticipantControlEffectOperation,
    request: ControlEffectRequestV2Model,
    context: ParticipantControlContextModel,
) -> bool:
    if request.target.kind == "inject":
        return _binds_inject(operation, request.target)
    intent = operation.intent
    target = request.target
    if (
        not _cancel_target(target)
        or not isinstance(intent, ParticipantCancellationControlIntent)
        or intent.application is None
    ):
        return False
    return (
        operation.participant_address,
        intent.episode_id,
        intent.target_kind.value,
        intent.target_ref,
        str(intent.target_revision),
        intent.application.policy_ref,
    ) == (
        context.participant_address,
        context.episode_id,
        "attempt",
        target.target_ref,
        target.expected_revision,
        target.lifecycle_authority.ref,
    )


def _cancel_target(target: ControlEffectTarget) -> bool:
    return target.kind == "interrupt" and target.operation == "cancel" and target.target_kind == "execution"


def _binds_inject(operation: ParticipantControlEffectOperation, target: ControlInjectEffectModel) -> bool:
    world = _scheduled_inject(operation.inject_request)
    if world is None or target.world_request is None or world != target.world_request:
        return False
    if operation.inject_application is not None and not _inject_application_matches(operation, target):
        return False
    return (world.inject, world.placement.event, world.placement.script, world.placement.story) == (
        target.inject_ref,
        target.event_ref,
        target.script_ref,
        target.story_ref,
    )


def _scheduled_inject(world: InjectTriggerRequestModel | None) -> InjectTriggerRequestModel | None:
    if not isinstance(world, InjectTriggerRequestModel) or world.placement.kind != "schedule":
        return None
    return InjectTriggerRequestModel.model_validate(world.model_dump(mode="json"))


def _inject_application_matches(operation: ParticipantControlEffectOperation, target: ControlInjectEffectModel) -> bool:
    application = operation.inject_application
    return (
        application.participant_address,
        application.episode_id,
        application.delivery_address,
        application.delivery_digest,
    ) == (target.participant_address, target.episode_id, target.delivery_ref.ref, target.delivery_ref.digest)


def submit_owned_effect(
    plane: RuntimeControlPlane,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestV2Model,
    operation: ParticipantControlEffectOperation,
    principal: ControlPlaneIdentity,
) -> None:
    key = owner_idempotency_key(claim)
    if isinstance(request.target, ControlInjectEffectModel):
        world = InjectTriggerRequestModel.model_validate(request.target.world_request.model_dump(mode="json"))
        receipt = plane.submit_inject(world, identity=principal)
        if not receipt.accepted or receipt.context.parent_operation_id != claim.receipt.operation_id:
            raise ConflictError("inject effect owner refused admission")
        # World and participant delivery have distinct owners and outcomes.
        # A disclosure retry never resubmits a world occurrence.
        if (
            operation.inject_application is not None
            and plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        ):
            from .participant_inject_application import submit_inject_effect

            application = operation.inject_application.model_copy(
                update={
                    "world_operation_id": receipt.operation_id,
                    "expected_snapshot_revision": plane._snapshot_state.revision,
                }
            )
            submit_inject_effect(plane, application, request.target, principal, key + ":delivery")
        return
    receipt = plane.record_participant_control(
        operation.participant_address,
        operation.intent,
        identity=principal,
        crossing_evidence=operation.crossing_evidence,
        idempotency_key=key,
    )
    if plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED:
        plane.dispatch_participant_cancellation(receipt.operation_id, identity=principal)


def owned_effect_outcome(
    plane: RuntimeControlPlane,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestV2Model,
    owner: ControlPlaneOperationRecord,
) -> str:
    if request.target.kind == "inject":
        return _inject_outcome(owner)
    if owner.status.state is OperationState.FAILED:
        return "failed"
    return _cancellation_outcome(plane, claim, request, owner)


def _inject_outcome(owner: ControlPlaneOperationRecord) -> str:
    if owner.inject_outcome is not None and owner.inject_evidence is not None:
        return {
            "effect-applied": "applied",
            "effect-absent": "failed",
            "known-partial": "failed",
            "indeterminate": "indeterminate",
        }[owner.inject_outcome.effect]
    return "failed" if owner.status.state is OperationState.FAILED else "indeterminate"


def _cancellation_outcome(
    plane: RuntimeControlPlane,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestV2Model,
    owner: ControlPlaneOperationRecord,
) -> str:
    from .participant_control_receipts import origin_principal

    link = (owner.result_payload or {}).get("participant_control_cancellation")
    if link is None or link["target_ref"] != request.target.target_ref:
        return "indeterminate"
    principal = origin_principal(plane, claim, link["participant_address"])
    status = plane.participant_cancellation_status(owner.receipt.operation_id, identity=principal)
    effect = status.cancellation_effect
    if effect is None:
        return "indeterminate"
    return {"prevented": "applied", "too-late": "failed", "partial-limitation": "indeterminate"}.get(
        effect.value, "indeterminate"
    )


def supports_effect_operation(
    plane: RuntimeControlPlane,
    request: ControlEffectRequestV2Model,
    operation: object,
    context: ParticipantControlContextModel,
    origin: ControlPlaneOperationRecord | None,
) -> bool:
    from .participant_control_effects import ParticipantControlEffectOperation, _binds_request
    from .participant_control_receipts import origin_principal

    if (
        origin is None
        or not isinstance(operation, ParticipantControlEffectOperation)
        or operation.kind != request.target.kind
        or not _binds_request(operation, request, context)
    ):
        return False
    principal = origin_principal(plane, origin, context.participant_address)
    if request.target.kind == "inject":
        return (
            plane._inject_execution is not None
            and plane._operation_evidence is not None
            and plane._distributed_execution is None
            and plane._target.orchestrator is not None
        )
    return _supports_control_operation(plane, request, operation, context, principal)


def _supports_control_operation(
    plane: RuntimeControlPlane,
    request: ControlEffectRequestV2Model,
    operation: ParticipantControlEffectOperation,
    context: ParticipantControlContextModel,
    principal: ControlPlaneIdentity,
) -> bool:
    from .participant_control_mediation import _specification_for_participant, _transition_for_intent

    try:
        specification = _specification_for_participant(plane, context.participant_address, principal)
        transition = _transition_for_intent(specification, operation.intent, principal)
    except ConflictError:
        return False
    if request.target.kind == "interrupt":
        supported = plane._mixed_control is not None
    elif request.target.kind == "handoff":
        states = {state.address: state for state in specification.controller_states}
        supported = (
            specification.mixed_control_participant_address == request.target.participant_address
            and transition.address == request.target.transition.ref
            and states[transition.from_state_address].controller_address == request.target.prior_controller_ref
            and states[transition.to_state_address].controller_address == request.target.resulting_controller_ref
        )
    else:
        supported = False
    return supported


def submit_effect_operation(
    control_plane: RuntimeControlPlane,
    claim: ControlPlaneOperationRecord,
    request: ControlEffectRequestModel | ControlEffectRequestV2Model,
    operation: ParticipantControlEffectOperation,
    *,
    principal: ControlPlaneIdentity,
) -> None:
    """Submit through the incumbent owner of this closed effect kind.

    The owner re-authorizes the principal it is given and claims its own
    operation under a key derived from this effect's claim, so its durable
    record — not the value returned here — carries the outcome.
    """

    if isinstance(request, ControlEffectRequestV2Model) and operation.kind in {"inject", "interrupt"}:
        submit_owned_effect(control_plane, claim, request, operation, principal)
        return
    idempotency_key = owner_idempotency_key(claim)
    if operation.kind == "inject":
        if operation.inject_application is not None:
            from .participant_inject_application import submit_inject_effect

            submit_inject_effect(
                control_plane, operation.inject_application, request.target, principal, idempotency_key
            )
            return
        control_plane.deliver_participant_directed_view(
            request.target.participant_address,
            operation.view,
            identity=principal,
            crossing_evidence=operation.crossing_evidence,
            idempotency_key=idempotency_key,
        )
        return
    control_plane.record_participant_control(
        request.target.participant_address,
        operation.intent,
        identity=principal,
        crossing_evidence=operation.crossing_evidence,
        idempotency_key=idempotency_key,
    )


# Pairs of (the owner input's coordinate, the admitted target's coordinate).
_Bindings = Sequence[tuple[object, object]]


def _inject_bindings(operation: ParticipantControlEffectOperation, target: object, context: object) -> _Bindings:
    if operation.inject_application is not None:
        application = operation.inject_application
        return [
            (application.participant_address, target.participant_address),
            (application.episode_id, target.episode_id),
            (application.delivery_address, target.delivery_ref.ref),
            (application.delivery_digest, target.delivery_ref.digest),
        ]
    view = operation.view
    return [
        (getattr(view, "participant_address", None), target.participant_address),
        (getattr(view, "episode_id", None), target.episode_id),
        (getattr(view, "view_id", None), target.result_item_ref),
        (getattr(view, "source_snapshot_ref", None), context.state_cut.cut_ref),
        (getattr(view, "visibility_projection_ref", None), target.disclosure_ref.ref),
    ]


def _handoff_bindings(operation: ParticipantControlEffectOperation, target: object, context: object) -> _Bindings:
    del context
    intent = operation.intent
    return (
        (getattr(intent, "kind", None), "handoff"),
        (getattr(intent, "episode_id", None), target.episode_id),
        (getattr(intent, "declaration_ref", None), target.transition.ref),
        (getattr(intent, "expected_state_revision", None), target.expected_state_revision),
        (getattr(intent, "completion_evidence_ref", None), target.completion_obligation.ref),
    )


# Every coordinate the closed target declares, paired with the owner input's own.
_OWNER_INPUT_BINDINGS = {"inject": _inject_bindings, "handoff": _handoff_bindings}


def owner_input_bindings(kind: str) -> Callable[[ParticipantControlEffectOperation, object, object], _Bindings] | None:
    return _OWNER_INPUT_BINDINGS.get(kind)

"""Closed joins to real inject and evidenced cancellation operations."""

from raes_contracts.contracts import InjectTriggerRequestModel
from raes_contracts.contracts.participant_control_decisions_v2 import ControlEffectRequestV2Model
from raes_contracts.contracts.participant_control_effects import ControlInjectEffectModel
from raes_contracts.runtime_state import OperationState

from .participant_control_intents import ParticipantCancellationControlIntent
from .participant_control_receipts import owner_idempotency_key


def prepare_v2_effect_dispatch(plane, binding, evaluation, origin, request):
    """Observe finished work; require current permission before any owner call."""
    from raes_contracts.contracts.participant_control_continuation import (
        validate_participant_control_effect_dispatch_v2,
    )

    from .control_plane_store_revision import SnapshotRevisionConflict
    from .participant_control_evaluation_v2 import _EvaluationCut
    from .participant_control_receipts import claim_outcome, realization, retained_effect_claim

    claim = retained_effect_claim(plane, origin, request)
    if claim is not None:
        disposition = claim_outcome(plane, claim, request)
        if disposition in {"applied", "failed"}:
            return realization(request, disposition, claim.receipt.operation_id), claim
    cut = _EvaluationCut.capture(plane, origin=origin)
    try:
        context = cut.call(binding.resolver.validation_context, evaluation)
        cut.call(lambda: validate_participant_control_effect_dispatch_v2(evaluation, request, context))
    except SnapshotRevisionConflict:
        raise
    except Exception:
        return realization(request, "withheld", "authority-unresolved." + request.effect_id), None
    return None


def resume_owned_effect(plane, claim, request):
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


def binds_owned_effect(operation, request, context):
    target = request.target
    if target.kind == "inject":
        world = operation.inject_request
        if not isinstance(world, InjectTriggerRequestModel) or world.placement.kind != "schedule":
            return False
        world = InjectTriggerRequestModel.model_validate(world.model_dump(mode="json"))
        if target.world_request is None or world != target.world_request:
            return False
        application = operation.inject_application
        if application is not None and (
            application.participant_address != target.participant_address
            or application.episode_id != target.episode_id
            or application.delivery_address != target.delivery_ref.ref
            or application.delivery_digest != target.delivery_ref.digest
        ):
            return False
        return (world.inject, world.placement.event, world.placement.script, world.placement.story) == (
            target.inject_ref,
            target.event_ref,
            target.script_ref,
            target.story_ref,
        )
    intent = operation.intent
    return (
        target.kind == "interrupt"
        and target.operation == "cancel"
        and target.target_kind == "execution"
        and isinstance(intent, ParticipantCancellationControlIntent)
        and intent.application is not None
        and operation.participant_address == context.participant_address
        and intent.episode_id == context.episode_id
        and intent.target_kind.value == "attempt"
        and intent.target_ref == target.target_ref
        and str(intent.target_revision) == target.expected_revision
        and target.lifecycle_authority.ref == intent.application.policy_ref
    )


def submit_owned_effect(plane, claim, request, operation, principal):
    key = owner_idempotency_key(claim)
    if isinstance(request.target, ControlInjectEffectModel):
        world = InjectTriggerRequestModel.model_validate(request.target.world_request.model_dump(mode="json"))
        receipt = plane.submit_inject(world, identity=principal)
        if not receipt.accepted or receipt.context.parent_operation_id != claim.receipt.operation_id:
            raise ValueError("inject effect owner refused admission")
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


def owned_effect_outcome(plane, claim, request, owner):
    if request.target.kind == "inject":
        if owner.inject_outcome is not None and owner.inject_evidence is not None:
            return {
                "effect-applied": "applied",
                "effect-absent": "failed",
                "known-partial": "failed",
                "indeterminate": "indeterminate",
            }[owner.inject_outcome.effect]
        return "failed" if owner.status.state is OperationState.FAILED else "indeterminate"
    if owner.status.state is OperationState.FAILED:
        return "failed"
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


def supports_effect_operation(plane, request, operation, context, origin):
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
    from .participant_control_mediation import _specification_for_participant, _transition_for_intent

    try:
        specification = _specification_for_participant(plane, context.participant_address, principal)
        transition = _transition_for_intent(specification, operation.intent, principal)
    except (ValueError, PermissionError):
        return False
    if request.target.kind == "interrupt":
        return plane._mixed_control is not None
    if request.target.kind == "handoff":
        states = {state.address: state for state in specification.controller_states}
        return (
            specification.mixed_control_participant_address == request.target.participant_address
            and transition.address == request.target.transition.ref
            and states[transition.from_state_address].controller_address == request.target.prior_controller_ref
            and states[transition.to_state_address].controller_address == request.target.resulting_controller_ref
        )
    return False


def submit_effect_operation(
    control_plane: object,
    claim,
    request,
    operation,
    *,
    principal: object,
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

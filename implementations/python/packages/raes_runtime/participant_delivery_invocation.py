"""Admission, bounded invocation and terminal settlement of participant delivery."""

from asyncio import CancelledError
from dataclasses import replace
from uuid import uuid4

from raes_contracts.contracts.participant_delivery_invocation import (
    ParticipantDeliveryInvocationContextModel,
    ParticipantDeliveryInvocationOutcomeModel,
)
from raes_contracts.contracts.participant_invocation_tools import delivery_tool_actions_enabled
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.runtime_state import OperationKind, OperationState
from raes_contracts.timestamps import isoformat_z

from .participant_inject_temporal import require_delivery_time

_LOGGER = get_logger(__name__)
_UNAVAILABLE = "participant delivery invocation is unavailable"


def invoke_delivery(plane, request, identity):
    capability = plane.delivery_target.manifest.participant_runtime
    if (
        plane.delivery_inject_delivery is None
        or capability is None
        or not delivery_tool_actions_enabled(capability.invocation_tool_actions)
    ):
        raise ConflictError(_UNAVAILABLE)
    retained = plane.delivery_operations.get(request.delivery_operation_id)
    if retained is None or retained.inject_delivery is None or retained.status.state is not OperationState.SUCCEEDED:
        raise ConflictError("delivery invocation requires a retained successful delivery")
    if not plane.delivery_operation_read_allowed(retained, identity):
        raise ConflictError("delivery invocation authority differs")
    content = retained.inject_delivery
    delivery = plane.delivery_authorized_delivery_binding(content.application, identity)
    if request.implementation_selection.participant_address != content.participant_address:
        raise ConflictError("delivery invocation participant differs")
    context = plane.delivery_operation_admission_context(
        kind=OperationKind.COMPOSITION_PHASE, request=request, identity=identity
    )
    key = "delivery-invocation:" + retained.receipt.operation_id
    existing = plane.delivery_store.find_by_idempotency(key, context=context)
    if existing is not None:
        if existing.receipt.context != context or existing.request_fingerprint != context.request_commitment:
            raise ConflictError("delivery invocation retry conflicts")
        return existing.receipt
    live = plane.delivery_snapshot.participant_episode_results.get(content.participant_address, {})
    if (live.get("episode_id"), live.get("status")) != (content.episode_id, "running"):
        raise ConflictError("delivery invocation episode is not running")
    require_delivery_time(plane.delivery_inject_delivery.model, delivery, plane.delivery_snapshot)
    if not callable(getattr(plane.delivery_inject_delivery.resolver, "resolve_invocation_cut", None)):
        raise ConflictError("delivery invocation live-cut owner is unavailable")
    operation_id, now = "participant.delivery-invocation." + str(uuid4()), isoformat_z(plane.wall_clock())
    invocation = ParticipantDeliveryInvocationContextModel(
        invocation_id=operation_id,
        delivery_operation_ref=retained.receipt.operation_id,
        delivery=content,
        implementation_manifest=request.implementation_manifest,
        implementation_selection=request.implementation_selection,
        execution_scope_ref=operation_id,
        execution_generation=plane.delivery_execution_generation,
    )
    record = plane.delivery_invocation_record(operation_id, now, context, key, invocation)
    claimed = plane.delivery_claim_record(record)
    if claimed.receipt.operation_id != operation_id:
        return claimed.receipt
    return _execute(plane, invocation, record, identity)


def _execute(plane, invocation, record, identity):
    scope = plane.delivery_mutation_authority.invocation_child_scope()
    tools = None
    outcome, failure = None, None
    try:
        tools = plane.delivery_tool_port_type(plane, invocation, scope, record, identity)
        with plane.delivery_mutation_authority.external_call():
            returned = plane.delivery_execution_adapter.call(
                "effect",
                plane.delivery_target.participant_runtime.invoke_delivery,
                invocation.model_copy(deep=True),
                tools,
                timeout_ms=plane.delivery_supervision.execution_ms,
            )
        if not isinstance(returned, ParticipantDeliveryInvocationOutcomeModel):
            raise ValueError("delivery invocation outcome is invalid")
        outcome = ParticipantDeliveryInvocationOutcomeModel.model_validate(returned.model_dump(mode="json"))
    except BaseException as exc:
        failure = exc
        if isinstance(exc, Exception):
            _LOGGER.exception(
                "participant delivery invocation did not establish its outcome", exc_info=foreign_failure_record(exc)
            )
    finally:
        scope.close()
        if tools is not None:
            tools.finish()
    plane.delivery_reload_derived_state()
    state = (
        OperationState.INDETERMINATE
        if outcome is None or tools is None or tools.has_unresolved_effects
        else OperationState(outcome.status)
    )
    diagnostics = (
        []
        if state is OperationState.SUCCEEDED
        else [
            Diagnostic(
                code="runtime.participant-delivery-invocation-failed",
                domain="participant",
                address=invocation.participant_address,
                message="The delivery invocation did not establish a successful terminal outcome.",
            )
        ]
    )
    terminal = replace(
        record,
        status=replace(record.status, state=state, updated_at=isoformat_z(plane.wall_clock()), diagnostics=diagnostics),
        result_payload={
            **record.result_payload,
            "outcome": None if outcome is None else outcome.model_dump(mode="json"),
        },
    )
    plane.delivery_commit_invocation_terminal(terminal)
    if isinstance(failure, CancelledError) or failure is not None and not isinstance(failure, Exception):
        raise failure
    return record.receipt

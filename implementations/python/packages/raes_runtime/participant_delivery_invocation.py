"""Admission, bounded invocation and terminal settlement of participant delivery."""

from asyncio import CancelledError
from dataclasses import replace
from uuid import uuid4

from raes_contracts.contracts.participant_delivery_invocation import (
    ParticipantDeliveryInvocationContextModel,
    ParticipantDeliveryInvocationOutcomeModel,
    ParticipantDeliveryInvocationRequestModel,
)
from raes_contracts.contracts.participant_invocation_tools import delivery_tool_actions_enabled
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.errors import ConflictError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationKind, OperationReceipt, OperationState, OperationStatus
from raes_contracts.timestamps import isoformat_z

from .control_plane_lifecycle import runtime_owned
from .control_plane_mutation import control_plane_mutation, mutation_entry
from .control_plane_operation_context import operation_admission_context
from .control_plane_security import ControlPlaneIdentity
from .control_plane_store import ControlPlaneOperationRecord, TerminalCommitMode
from .participant_delivery_tools import ParticipantDeliveryInvocationTools
from .participant_inject_application import _authorized_binding
from .participant_inject_temporal import require_delivery_time

_LOGGER = get_logger(__name__)
_UNAVAILABLE = "participant delivery invocation is unavailable"


class ParticipantDeliveryInvocationMixin:
    @runtime_owned
    @mutation_entry(OperationKind.COMPOSITION_PHASE)
    def invoke_participant_delivery(
        self,
        request: ParticipantDeliveryInvocationRequestModel,
        *,
        identity: ControlPlaneIdentity | None,
    ) -> OperationReceipt:
        if not isinstance(request, ParticipantDeliveryInvocationRequestModel):
            raise TypeError("delivery invocation requires a typed request")
        request = ParticipantDeliveryInvocationRequestModel.model_validate(request.model_dump(mode="json"))
        with control_plane_mutation(self, OperationKind.COMPOSITION_PHASE):
            self._reload_derived_state()
            return _invoke(self, request, identity)


def _invoke(plane, request, identity):
    capability = plane._target.manifest.participant_runtime
    if (
        plane._inject_delivery is None
        or capability is None
        or not delivery_tool_actions_enabled(capability.invocation_tool_actions)
    ):
        raise ConflictError(_UNAVAILABLE)
    retained = plane._operations.get(request.delivery_operation_id)
    if retained is None or retained.inject_delivery is None or retained.status.state is not OperationState.SUCCEEDED:
        raise ConflictError("delivery invocation requires a retained successful delivery")
    if not plane._operation_read_allowed(retained, identity):
        raise ConflictError("delivery invocation authority differs")
    content = retained.inject_delivery
    delivery = _authorized_binding(plane, content.application, identity)
    if request.implementation_selection.participant_address != content.participant_address:
        raise ConflictError("delivery invocation participant differs")
    context = operation_admission_context(
        plane, kind=OperationKind.COMPOSITION_PHASE, request=request, identity=identity
    )
    key = "delivery-invocation:" + retained.receipt.operation_id
    existing = plane._store.find_by_idempotency(key, context=context)
    if existing is not None:
        if existing.receipt.context != context or existing.request_fingerprint != context.request_commitment:
            raise ConflictError("delivery invocation retry conflicts")
        return existing.receipt
    live = plane._snapshot.participant_episode_results.get(content.participant_address, {})
    if (live.get("episode_id"), live.get("status")) != (content.episode_id, "running"):
        raise ConflictError("delivery invocation episode is not running")
    require_delivery_time(plane._inject_delivery.model, delivery, plane._snapshot)
    if not callable(getattr(plane._inject_delivery.resolver, "resolve_invocation_cut", None)):
        raise ConflictError("delivery invocation live-cut owner is unavailable")
    operation_id, now = "participant.delivery-invocation." + str(uuid4()), isoformat_z(plane.wall_clock())
    invocation = ParticipantDeliveryInvocationContextModel(
        invocation_id=operation_id,
        delivery_operation_ref=retained.receipt.operation_id,
        delivery=content,
        implementation_manifest=request.implementation_manifest,
        implementation_selection=request.implementation_selection,
        execution_scope_ref=operation_id,
        execution_generation=plane._execution_generation,
    )
    record = ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at=now,
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            state=OperationState.RUNNING,
            submitted_at=now,
            updated_at=now,
            context=context,
        ),
        request_fingerprint=context.request_commitment,
        idempotency_key=key,
        result_payload={"kind": "participant-delivery-invocation/v1", "binding": invocation.model_dump(mode="json")},
    )
    claimed = plane._claim_record(record)
    if claimed.receipt.operation_id != operation_id:
        return claimed.receipt
    return _execute(plane, invocation, record, identity)


def _execute(plane, invocation, record, identity):
    scope = plane._mutation_authority.invocation_child_scope()
    tools = None
    outcome, failure = None, None
    try:
        tools = ParticipantDeliveryInvocationTools(plane, invocation, scope, record, identity)
        with plane._mutation_authority.external_call():
            returned = plane._execution_adapter.call(
                "effect",
                plane._target.participant_runtime.invoke_delivery,
                invocation.model_copy(deep=True),
                tools,
                timeout_ms=plane._supervision.execution_ms,
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
    plane._reload_derived_state()
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
    plane._commit_terminal_operation(plane._snapshot, terminal, mode=TerminalCommitMode.OPERATION_ONLY)
    if isinstance(failure, CancelledError) or failure is not None and not isinstance(failure, Exception):
        raise failure
    return record.receipt

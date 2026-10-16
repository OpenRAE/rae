"""Execute the published backend protocol through RAE's admitted state cuts."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from time import monotonic
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    BackendOperationCapabilitiesModel,
    BackendOperationResponseModel,
    require_backend_execution_policy_admission,
    require_backend_operation_admission,
    require_inject_occurrence_invocation,
    validate_backend_operation_response,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState

from .backend_calls import _BackendCallContext, _RealizationApplyContext
from .backend_observation_calls import _ObservationApplyRequest
from .control_plane_execution import _utc_now
from .control_plane_store import ControlPlaneOperationRecord
from .control_plane_supervised_execution import claim_accepted, invocation_request, settle
from .control_plane_supervision import persist_invocation_update
from .operation_command_commitment import native_command_commitment
from .operation_result_finalization import finalize_protocol_result
from .operation_transcript_policy import automatic_poll_interval_ms

if TYPE_CHECKING:
    from raes_contracts.contracts import BackendOperationControlModel, BackendOperationRequestModel
    from raes_contracts.runtime_state import ApplyResult, OperationReceipt, RuntimeSnapshot

    from .control_plane import RuntimeControlPlane
    from .control_plane_execution import OperationExecutionRequest
    from .operation_execution_adapter import Lane
    from .operation_supervision_configuration import OperationEvidenceResolver


def provider_call(
    plane: RuntimeControlPlane,
    method: Callable[..., object],
    *,
    budget_ms: int,
    allowed: set[str] | None = None,
    request: BackendOperationRequestModel | None = None,
    control: BackendOperationControlModel | None = None,
    lane: Lane = "effect",
) -> BackendOperationCapabilitiesModel | BackendOperationResponseModel:
    arguments = ()
    if allowed is not None:
        arguments = (request,) if control is None else (control,)
    with plane._mutation_authority.external_call():
        value = plane._execution_adapter.call(lane, method, *arguments, timeout_ms=budget_ms)
        model = BackendOperationCapabilitiesModel if allowed is None else BackendOperationResponseModel
        if not isinstance(value, model):
            raise ValueError("provider returned an invalid operation carrier")
        value = model.model_validate(value.model_dump(mode="json"))
        if allowed is not None:
            if value.message.kind not in allowed:
                raise ValueError("provider method returned an invalid message kind")
            validate_backend_operation_response(request, value, control=control)
        return value


def accept_response(
    plane: RuntimeControlPlane,
    record: ControlPlaneOperationRecord,
    response: BackendOperationResponseModel,
    *,
    control: BackendOperationControlModel | None = None,
) -> ControlPlaneOperationRecord:
    plane._reload_derived_state()
    current = plane._operations[record.receipt.operation_id]
    validate_backend_operation_response(current.invocation.request, response, control=control)
    for previous in current.invocation.responses:
        if previous.sequence == response.sequence:
            if previous != response:
                raise ValueError("duplicate response changed its content")
            return current
    actor = None
    if hasattr(response.message, "control_id"):
        actor = next(
            item.actor_id for item in current.invocation.controls if item.control_id == response.message.control_id
        )
    return persist_invocation_update(
        plane,
        current,
        current.invocation.model_copy(update={"responses": (*current.invocation.responses, response)}),
        actor=actor,
    )


def validate_outcome(
    plane: RuntimeControlPlane,
    record: ControlPlaneOperationRecord,
    response: BackendOperationResponseModel,
    native_request: OperationExecutionRequest,
    predecessor: RuntimeSnapshot,
) -> tuple[ApplyResult | None, str | None, dict[str, object] | None]:
    if record.invocation.request.command.digest != native_command_commitment(plane, native_request.plan):
        raise ValueError("admitted native command changed before finalization")
    resolver = plane._operation_evidence
    if resolver is None:
        raise ValueError("operation evidence authority is not installed")
    message = response.message
    deadline = monotonic() + plane._supervision.observation_ms / 1000
    execution_deadline = plane._execution_deadlines.get(record.receipt.operation_id)
    if execution_deadline is not None and record.status.state is OperationState.RUNNING:
        deadline = min(deadline, execution_deadline)

    def remaining() -> int:
        budget = int((deadline - monotonic()) * 1000)
        if budget <= 0:
            raise TimeoutError("operation evidence budget exhausted")
        return budget

    with plane._mutation_authority.external_call():
        verified = plane._execution_adapter.call(
            "effect",
            resolver.validate_effects,
            record.invocation.request,
            response,
            timeout_ms=remaining(),
        )
        if verified is not True:
            raise ValueError("operation effect evidence could not be established")
        if message.proposed_state is OperationState.INDETERMINATE:
            return None, None, None
        if (
            message.effects.effect == "absent"
            and message.result is None
            and message.proposed_state is not OperationState.SUCCEEDED
        ):
            return None, canonical_json_digest(message.effects.model_dump(mode="json")), None
        return _finalize_native_outcome(plane, record, response, native_request, predecessor, remaining, resolver)


def _finalize_native_outcome(
    plane: RuntimeControlPlane,
    record: ControlPlaneOperationRecord,
    response: BackendOperationResponseModel,
    native_request: OperationExecutionRequest,
    predecessor: RuntimeSnapshot,
    remaining: Callable[[], int],
    resolver: OperationEvidenceResolver,
) -> tuple[ApplyResult, str, dict[str, object] | None]:
    message = response.message
    result = plane._execution_adapter.call(
        "effect",
        resolver.resolve_result,
        record.invocation.request,
        response,
        deepcopy(predecessor),
        timeout_ms=remaining(),
    )
    reference = message.result or message.effects.residual_state
    if reference is None or reference.contract_id != "runtime-snapshot-v1":
        raise ValueError("native result reference is missing or unsupported")
    accepted, payload = plane._execution_adapter.call(
        "effect",
        finalize_protocol_result,
        result,
        reference,
        message.proposed_state,
        timeout_ms=remaining(),
        observation_request=_ObservationApplyRequest(
            address=native_request.address,
            snapshot=predecessor,
            plan=native_request.plan,
            manifest=plane._target.manifest,
            runtime=plane._target.observation_runtime,
            durable_lifecycle_available=plane._store_commits.crash_atomic,
            operation_id=record.receipt.operation_id,
            materialization_archive=plane._materialization_archive,
        ),
        realization=_RealizationApplyContext(
            plan=native_request.plan if isinstance(native_request.plan, ProvisioningPlan) else None,
            operation_plan=native_request.plan,
            manifest=plane._target.manifest,
        ),
        call=_BackendCallContext(
            information_state_context_resolver=plane._information_state_context_resolver,
            materialization_archive=plane._materialization_archive,
        ),
    )
    commitment = canonical_json_digest(message.effects.model_dump(mode="json"))
    return accepted, commitment, payload


def execute_provider_operation(
    plane: RuntimeControlPlane, native_request: OperationExecutionRequest
) -> OperationReceipt:
    operation_id = (
        native_request.inject_occurrence.operation_id
        if native_request.inject_occurrence is not None
        else getattr(native_request.plan, "operation_id", None) or str(uuid4())
    )
    backend_request = invocation_request(plane, native_request, operation_id, _utc_now())
    deadline = monotonic() + backend_request.budget.remaining_ms / 1000

    def remaining() -> int:
        budget = int((deadline - monotonic()) * 1000)
        if budget <= 0:
            raise TimeoutError("execution budget exhausted")
        return budget

    record = None
    try:
        capabilities, admission = _check_provider_admission(plane, backend_request, remaining)
        _require_provider_policy(plane, native_request, backend_request, capabilities, admission)
        record, receipt = claim_accepted(
            plane,
            native_request,
            backend_request=backend_request,
            native=False,
            responses=(admission,),
        )
        if record is not None:
            predecessor = deepcopy(plane._snapshot)
            if plane._distributed_execution is not None:
                _deliver_provider_invocation(
                    plane, native_request, backend_request, record, predecessor, deadline, remaining
                )
            else:
                running = _start_local_provider(plane, native_request, backend_request, record, deadline, remaining)
                if running is not None:
                    _poll_provider_outcome(plane, native_request, running, predecessor, remaining)
        return receipt
    except Exception:
        return _classify_provider_failure(plane, native_request, record)


def _check_provider_admission(
    plane: RuntimeControlPlane, request: BackendOperationRequestModel, remaining: Callable[[], int]
) -> tuple[BackendOperationCapabilitiesModel, BackendOperationResponseModel]:
    provider = plane._target.operation_provider
    capabilities = provider_call(
        plane,
        provider.operation_capabilities,
        budget_ms=min(remaining(), plane._supervision.admission_ms),
    )
    admission = provider_call(
        plane,
        provider.check_operation,
        budget_ms=min(remaining(), plane._supervision.admission_ms),
        allowed={"admission"},
        request=request,
    )
    return cast(BackendOperationCapabilitiesModel, capabilities), cast(BackendOperationResponseModel, admission)


def _require_provider_policy(
    plane: RuntimeControlPlane,
    native_request: OperationExecutionRequest,
    request: BackendOperationRequestModel,
    capabilities: BackendOperationCapabilitiesModel,
    admission: BackendOperationResponseModel,
) -> None:
    if native_request.inject_occurrence is not None:
        from raes_contracts.contracts.backend_operation_validation import require_backend_plan_policy_capabilities

        from .inject_execution import InjectAdmission, require_inject_plan

        require_inject_plan(plane, InjectAdmission(native_request.plan, native_request.inject_occurrence))
        require_inject_occurrence_invocation(native_request.inject_occurrence, request)
        require_backend_plan_policy_capabilities(native_request.plan, capabilities)
        require_backend_operation_admission(request, capabilities, admission)
        return
    require_backend_execution_policy_admission(
        request,
        capabilities,
        admission,
        native_request.plan,
        resolved_native_plan_commitment=native_command_commitment(plane, native_request.plan),
    )


def _deliver_provider_invocation(
    plane: RuntimeControlPlane,
    native_request: OperationExecutionRequest,
    request: BackendOperationRequestModel,
    record: ControlPlaneOperationRecord,
    predecessor: RuntimeSnapshot,
    deadline: float,
    remaining: Callable[[], int],
) -> None:
    from .operation_temporal import EngineDeliveryBinding

    with plane._mutation_authority.external_call():
        delivery = EngineDeliveryBinding.model_validate(
            plane._execution_adapter.call(
                "effect",
                plane._distributed_execution.binding,
                request,
                timeout_ms=min(remaining(), plane._supervision.admission_ms),
            )
        )
    record = persist_invocation_update(plane, record, record.invocation.model_copy(update={"delivery": delivery}))
    plane._admitted_backend_requests[record.receipt.operation_id] = (native_request, predecessor)
    plane._execution_deadlines[record.receipt.operation_id] = deadline
    plane._execution_adapter.arm_deadline(
        record.receipt.operation_id,
        deadline,
        plane._expire_backend_invocation,
        request.binding,
        failure_handler=plane._poison_runtime_durability,
    )
    with plane._mutation_authority.external_call():
        engine_id = plane._execution_adapter.call(
            "effect",
            plane._distributed_execution.submit,
            request,
            timeout_ms=min(remaining(), plane._supervision.admission_ms),
        )
    if engine_id != delivery.workflow_id:
        raise ValueError("engine acknowledgement changed its delivery binding")


def _start_local_provider(
    plane: RuntimeControlPlane,
    native_request: OperationExecutionRequest,
    request: BackendOperationRequestModel,
    record: ControlPlaneOperationRecord,
    deadline: float,
    remaining: Callable[[], int],
) -> ControlPlaneOperationRecord | None:
    # Admission may have waited. Recheck willingness and the exact capability
    # declaration immediately before the one-use transaction.
    capabilities, admission = _check_provider_admission(plane, request, remaining)
    record = accept_response(plane, record, admission)
    _require_provider_policy(plane, native_request, request, capabilities, admission)
    if native_request.admission_diagnostics is not None and native_request.admission_diagnostics():
        raise ValueError("live operation admission was withdrawn")
    plane._reload_derived_state()
    record = plane._operations[record.receipt.operation_id]
    if record.status.state is not OperationState.ACCEPTED:
        return None
    if plane._effect_admission_stopped or plane._store.effect_admission_stopped():
        settle(plane, record, OperationState.CANCELLED)
        return None
    remaining()
    running = cast(
        ControlPlaneOperationRecord,
        replace(
            record,
            status=replace(record.status, state=OperationState.RUNNING, updated_at=_utc_now()),
            invocation=record.invocation.model_copy(update={"consumed": True}),
        ),
    )
    try:
        plane._store.save_record(running)
    except BaseException:
        plane._poison_runtime_durability()
        raise
    plane._execution_deadlines[record.receipt.operation_id] = deadline
    acknowledgement = cast(
        BackendOperationResponseModel,
        provider_call(
            plane,
            plane._target.operation_provider.start_operation,
            budget_ms=remaining(),
            allowed={"acknowledgement"},
            request=request,
            lane="effect",
        ),
    )
    record = accept_response(plane, running, acknowledgement)
    if acknowledgement.message.disposition == "refused":
        # Consumed permission still needs independent absence/cessation evidence.
        settle(plane, record, OperationState.INDETERMINATE)
        record = None
    return record


def _settle_provider_outcome(
    plane: RuntimeControlPlane,
    native_request: OperationExecutionRequest,
    record: ControlPlaneOperationRecord,
    predecessor: RuntimeSnapshot,
    response: BackendOperationResponseModel,
    remaining: Callable[[], int],
) -> None:
    if record.inject_occurrence is not None:
        from .inject_outcomes import settle_inject_outcome

        settle_inject_outcome(plane, record, response, remaining)
        return
    result, commitment, payload = validate_outcome(plane, record, response, native_request, predecessor)
    settle(
        plane,
        record,
        response.message.proposed_state,
        result=result,
        release_commitment=commitment,
        diagnostics=() if result is None else result.diagnostics,
        result_payload=payload,
    )


def _poll_provider_outcome(
    plane: RuntimeControlPlane,
    native_request: OperationExecutionRequest,
    record: ControlPlaneOperationRecord,
    predecessor: RuntimeSnapshot,
    remaining: Callable[[], int],
) -> None:
    while True:
        response_cursor = len(record.invocation.responses)
        control = plane.supervise_operation(
            record.receipt.operation_id,
            action="observe",
            control_id=str(uuid4()),
            identity=None,
            _automatic_observation=True,
        )
        # Consume the retained response of this persisted observer, never a
        # second provider call with the same consumed control identity.
        plane._reload_derived_state()
        record = plane._operations[record.receipt.operation_id]
        new_responses = record.invocation.responses[response_cursor:]
        response = next(
            (item for item in new_responses if item.message.kind == "outcome"),
            new_responses[-1] if new_responses else None,
        )
        if control.control_id not in record.invocation.delivered_controls or response is None:
            raise ValueError("operation observation is unavailable")
        if response.message.kind == "outcome":
            _settle_provider_outcome(plane, native_request, record, predecessor, response, remaining)
            return
        if response.message.kind in {"control", "reconciliation"}:
            raise ValueError("operation outcome could not be established")
        with plane._mutation_authority.external_call():
            plane._execution_adapter.pause(
                min(
                    remaining(),
                    automatic_poll_interval_ms(record.invocation.request.budget.limit_ms),
                )
            )


def _classify_provider_failure(
    plane: RuntimeControlPlane, native_request: OperationExecutionRequest, record: ControlPlaneOperationRecord | None
) -> OperationReceipt:
    if plane._durability_poisoned:
        raise
    if record is None:
        return plane._reject_diagnostics(
            domain=native_request.domain,
            context=native_request.context,
            diagnostics=[
                Diagnostic(
                    code="runtime.control-plane.backend-admission-refused",
                    domain="runtime",
                    address="runtime.control-plane",
                    message="Backend operation admission could not be established.",
                )
            ],
        )
    plane._reload_derived_state()
    current = plane._operations[record.receipt.operation_id]
    if current.status.state in {OperationState.ACCEPTED, OperationState.RUNNING}:
        settle(
            plane, current, OperationState.INDETERMINATE if current.invocation.consumed else OperationState.CANCELLED
        )
    return record.receipt


__all__ = ("execute_provider_operation", "accept_response", "provider_call", "validate_outcome")

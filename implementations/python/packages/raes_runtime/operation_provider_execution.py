"""Execute the published backend protocol through RAE's admitted state cuts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from time import monotonic
from uuid import uuid4

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    BackendOperationCapabilitiesModel,
    BackendOperationResponseModel,
    require_backend_execution_policy_admission,
    validate_backend_operation_response,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState

from .backend_calls import _BackendCallContext, _RealizationApplyContext
from .backend_observation_calls import _ObservationApplyRequest
from .control_plane_execution import _utc_now
from .control_plane_supervised_execution import claim_accepted, invocation_request, settle
from .control_plane_supervision import persist_invocation_update
from .operation_command_commitment import native_command_commitment
from .operation_result_finalization import finalize_protocol_result
from .operation_transcript_policy import automatic_poll_interval_ms


def provider_call(plane, method, *args, budget_ms, allowed=None, request=None, control=None, lane="effect"):
    with plane._mutation_authority.external_call():
        value = plane._execution_adapter.call(lane, method, *args, timeout_ms=budget_ms)
        model = BackendOperationCapabilitiesModel if allowed is None else BackendOperationResponseModel
        if not isinstance(value, model):
            raise ValueError("provider returned an invalid operation carrier")
        value = model.model_validate(value.model_dump(mode="json"))
        if allowed is not None:
            if value.message.kind not in allowed:
                raise ValueError("provider method returned an invalid message kind")
            validate_backend_operation_response(request, value, control=control)
        return value


def accept_response(plane, record, response, *, control=None):
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


def validate_outcome(plane, record, response, native_request, predecessor):
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

    def remaining():
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


def execute_provider_operation(plane, native_request):
    provider = plane._target.operation_provider
    operation_id = getattr(native_request.plan, "operation_id", None) or str(uuid4())
    backend_request = invocation_request(plane, native_request, operation_id, _utc_now())
    deadline = monotonic() + backend_request.budget.remaining_ms / 1000

    def remaining():
        budget = int((deadline - monotonic()) * 1000)
        if budget <= 0:
            raise TimeoutError("execution budget exhausted")
        return budget

    record = None
    try:
        capabilities = provider_call(
            plane, provider.operation_capabilities, budget_ms=min(remaining(), plane._supervision.admission_ms)
        )
        admission = provider_call(
            plane,
            provider.check_operation,
            backend_request,
            budget_ms=min(remaining(), plane._supervision.admission_ms),
            allowed={"admission"},
            request=backend_request,
        )
        require_backend_execution_policy_admission(
            backend_request,
            capabilities,
            admission,
            native_request.plan,
            resolved_native_plan_commitment=native_command_commitment(plane, native_request.plan),
        )
        record, receipt = claim_accepted(
            plane,
            native_request,
            backend_request=backend_request,
            native=False,
            responses=(admission,),
        )
        if record is None:
            return receipt
        predecessor = deepcopy(plane._snapshot)
        if plane._distributed_execution is not None:
            from .operation_temporal import EngineDeliveryBinding

            with plane._mutation_authority.external_call():
                delivery = EngineDeliveryBinding.model_validate(
                    plane._execution_adapter.call(
                        "effect",
                        plane._distributed_execution.binding,
                        backend_request,
                        timeout_ms=min(remaining(), plane._supervision.admission_ms),
                    )
                )
            record = persist_invocation_update(
                plane, record, record.invocation.model_copy(update={"delivery": delivery})
            )
            plane._admitted_backend_requests[record.receipt.operation_id] = (native_request, predecessor)
            plane._execution_deadlines[record.receipt.operation_id] = deadline
            plane._execution_adapter.arm_deadline(
                record.receipt.operation_id,
                deadline,
                plane._expire_backend_invocation,
                backend_request.binding,
                failure_handler=plane._poison_runtime_durability,
            )
            with plane._mutation_authority.external_call():
                engine_id = plane._execution_adapter.call(
                    "effect",
                    plane._distributed_execution.submit,
                    backend_request,
                    timeout_ms=min(remaining(), plane._supervision.admission_ms),
                )
            if engine_id != delivery.workflow_id:
                raise ValueError("engine acknowledgement changed its delivery binding")
            return receipt
        # Admission may have waited. Fresh willingness and the exact capability
        # declaration are checked again before the one-use transaction.
        capabilities = provider_call(
            plane, provider.operation_capabilities, budget_ms=min(remaining(), plane._supervision.admission_ms)
        )
        admission = provider_call(
            plane,
            provider.check_operation,
            backend_request,
            budget_ms=min(remaining(), plane._supervision.admission_ms),
            allowed={"admission"},
            request=backend_request,
        )
        record = accept_response(plane, record, admission)
        require_backend_execution_policy_admission(
            backend_request,
            capabilities,
            admission,
            native_request.plan,
            resolved_native_plan_commitment=native_command_commitment(plane, native_request.plan),
        )
        plane._reload_derived_state()
        record = plane._operations[record.receipt.operation_id]
        if record.status.state is not OperationState.ACCEPTED:
            return receipt
        if plane._effect_admission_stopped or plane._store.effect_admission_stopped():
            settle(plane, record, OperationState.CANCELLED)
            return receipt
        remaining()
        running = replace(
            record,
            status=replace(record.status, state=OperationState.RUNNING, updated_at=_utc_now()),
            invocation=record.invocation.model_copy(update={"consumed": True}),
        )
        try:
            plane._store.save_record(running)
        except BaseException:
            plane._poison_runtime_durability()
            raise
        record = running
        plane._execution_deadlines[record.receipt.operation_id] = deadline
        acknowledgement = provider_call(
            plane,
            provider.start_operation,
            backend_request,
            budget_ms=remaining(),
            allowed={"acknowledgement"},
            request=backend_request,
            lane="effect",
        )
        record = accept_response(plane, record, acknowledgement)
        if acknowledgement.message.disposition == "refused":
            # The grant was already consumed. Shape/authentication alone cannot
            # independently account for its physical absence and cessation.
            settle(plane, record, OperationState.INDETERMINATE)
            return receipt
        while True:
            response_cursor = len(record.invocation.responses)
            control = plane.supervise_operation(
                record.receipt.operation_id,
                action="observe",
                control_id=str(uuid4()),
                identity=None,
                _automatic_observation=True,
            )
            # supervise_operation persisted and delivered this exact observer;
            # consume its retained response rather than issuing a second call.
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
                return receipt
            if response.message.kind in {"control", "reconciliation"}:
                raise ValueError("operation outcome could not be established")
            with plane._mutation_authority.external_call():
                plane._execution_adapter.pause(
                    min(remaining(), automatic_poll_interval_ms(backend_request.budget.limit_ms))
                )
    except Exception:
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
                plane,
                current,
                OperationState.INDETERMINATE if current.invocation.consumed else OperationState.CANCELLED,
            )
        return record.receipt


__all__ = ("execute_provider_operation", "accept_response", "provider_call", "validate_outcome")

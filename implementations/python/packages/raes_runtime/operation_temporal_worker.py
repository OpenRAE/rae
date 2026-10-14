"""Trusted activity workers obtain scoped live grants through the state authority."""

from __future__ import annotations

from time import monotonic

import anyio
from raes_contracts.contracts import (
    BackendOperationCapabilitiesModel,
    BackendOperationResponseModel,
    backend_operation_request_digest,
    require_backend_operation_admission,
    validate_backend_operation_response,
)
from temporalio import activity

from .operation_control_budget import ControlDeliveryGrant
from .operation_execution_adapter import LocalExecutionAdapter
from .operation_temporal import EngineOperationReference


class TemporalOperationActivities:
    """Backend integration code only; no ledger credentials or scenario interpreter."""

    def __init__(
        self,
        *,
        provider,
        effect_authority,
        control_authority,
        worker_identity: str,
        effect_capacity: int = 1,
        control_capacity: int = 2,
    ) -> None:
        self._provider = provider
        self._effect_authority = effect_authority
        self._control_authority = control_authority
        self._worker_identity = worker_identity
        self._executor = LocalExecutionAdapter(effect_capacity=effect_capacity, control_capacity=control_capacity)
        self._effect_jobs = LocalExecutionAdapter(effect_capacity=effect_capacity)
        self._control_jobs = LocalExecutionAdapter(control_capacity=control_capacity)
        self._offload_limiters = {
            "effect": anyio.CapacityLimiter(effect_capacity),
            "control": anyio.CapacityLimiter(control_capacity),
        }

    def _reference(self, payload):
        try:
            reference = EngineOperationReference.model_validate(payload)
        except Exception:
            raise ValueError("engine operation reference is invalid") from None
        if reference.worker_id != self._worker_identity:
            raise ValueError("engine reference belongs to another worker")
        return reference

    def _request(self, authority, reference):
        request = authority.get_request(reference)
        binding = request.binding
        if (
            binding.operation_id,
            binding.invocation_id,
            binding.deployment_id,
            binding.owner_generation,
            binding.execution_generation,
            binding.worker_id,
            backend_operation_request_digest(request),
        ) != (
            reference.operation_id,
            reference.invocation_id,
            reference.deployment_id,
            reference.owner_generation,
            reference.execution_generation,
            reference.worker_id,
            reference.request_digest,
        ):
            raise ValueError("engine reference does not match admitted authority")
        return request

    @activity.defn(name="raes.invoke")
    async def invoke(self, payload) -> str:
        reference = self._reference(payload)
        return await self._job(
            self._effect_jobs, "effect", self._invoke, reference, budget_ms=reference.execution_budget_ms
        )

    async def _job(self, executor, lane, method, *args, budget_ms):
        from .operation_execution_adapter import require_budget_ms

        deadline = monotonic() + require_budget_ms(budget_ms) / 1000

        def admitted():
            remaining = int((deadline - monotonic()) * 1000)
            if remaining <= 0:
                raise TimeoutError("activity allowance exhausted before admission")
            return executor.call(lane, method, *args, timeout_ms=remaining)

        try:
            with anyio.fail_after(budget_ms / 1000):
                return await anyio.to_thread.run_sync(
                    admitted, abandon_on_cancel=True, limiter=self._offload_limiters[lane]
                )
        except Exception:
            raise RuntimeError("backend activity could not be established") from None

    def _invoke(self, reference):
        authority, provider = self._effect_authority, self._provider
        try:
            request = self._request(authority, reference)
            capabilities = self._executor.call(
                "effect", provider.operation_capabilities, timeout_ms=reference.control_budget_ms
            )
            capabilities = BackendOperationCapabilitiesModel.model_validate(capabilities.model_dump(mode="json"))
            admission = self._executor.call(
                "effect", provider.check_operation, request, timeout_ms=reference.control_budget_ms
            )
            admission = BackendOperationResponseModel.model_validate(admission.model_dump(mode="json"))
            require_backend_operation_admission(request, capabilities, admission)
            # The state authority rechecks policy, ownership, willingness,
            # clock continuity and the unconsumed claim. A lost reply supplies
            # no grant; redelivery never returns the consumed permission.
            grant_started = monotonic()
            grant = authority.claim(reference, capabilities, admission)
            if grant.request != request:
                raise ValueError("invocation grant changed its admitted request")
            remaining = grant.remaining_budget_ms - int((monotonic() - grant_started) * 1000)
            if remaining <= 0:
                raise ValueError("invocation grant expired in delivery")
        except Exception:
            return self._control_authority.indeterminate(reference)
        try:
            response = self._executor.call("effect", provider.start_operation, request, timeout_ms=remaining)
            response = BackendOperationResponseModel.model_validate(response.model_dump(mode="json"))
            validate_backend_operation_response(request, response)
            if response.message.kind != "acknowledgement":
                raise ValueError("backend acknowledgement is invalid")
            return authority.publish(reference, response)
        except Exception:
            return self._control_authority.indeterminate(reference)

    @activity.defn(name="raes.observe")
    async def observe(self, payload) -> str:
        reference = self._reference(payload)
        return await self._job(
            self._control_jobs, "control", self._observe, reference, budget_ms=reference.control_budget_ms
        )

    def _observe(self, reference):
        authority = self._control_authority
        try:
            request = self._request(authority, reference)
            began = monotonic()
            grant = ControlDeliveryGrant.model_validate(authority.observation(reference))
            control = grant.control
            remaining = self._control_allowance(request, grant, began)
            if control.action != "observe":
                raise ValueError("worker observation grant is invalid")
            response = self._executor.call(
                "control",
                self._provider.observe_operation,
                control,
                timeout_ms=min(remaining, reference.control_budget_ms),
            )
            response = BackendOperationResponseModel.model_validate(response.model_dump(mode="json"))
            validate_backend_operation_response(request, response, control=control)
            if response.message.kind not in {"progress", "outcome", "control", "reconciliation"}:
                raise ValueError("backend observation is invalid")
            return authority.publish(reference, response)
        except Exception:
            return authority.indeterminate(reference)

    @activity.defn(name="raes.control")
    async def control(self, payload) -> str:
        reference = self._reference(payload["reference"])
        from pydantic import TypeAdapter
        from raes_contracts.contracts.backend_operation import OperationIdentifier

        control_id = TypeAdapter(OperationIdentifier).validate_python(payload["control_id"])
        return await self._job(
            self._control_jobs, "control", self._control, reference, control_id, budget_ms=reference.control_budget_ms
        )

    def _control(self, reference, control_id):
        authority = self._control_authority
        request = self._request(authority, reference)
        # Redelivery cannot reacquire a consumed control claim either.
        began = monotonic()
        grant = ControlDeliveryGrant.model_validate(authority.get_control(reference, control_id))
        control = grant.control
        remaining = self._control_allowance(request, grant, began)
        if control.control_id != control_id:
            raise ValueError("worker control grant is invalid")
        methods = {
            "cancel": self._provider.cancel_operation,
            "observe": self._provider.observe_operation,
            "reconcile": self._provider.reconcile_operation,
        }
        response = self._executor.call(
            "control",
            methods[control.action],
            control,
            timeout_ms=min(remaining, reference.control_budget_ms),
        )
        response = BackendOperationResponseModel.model_validate(response.model_dump(mode="json"))
        validate_backend_operation_response(request, response, control=control)
        allowed = {"control"} if control.action == "cancel" else {"progress", "outcome", "control", "reconciliation"}
        if response.message.kind not in allowed:
            raise ValueError("backend control response is invalid")
        return authority.publish(reference, response)

    @staticmethod
    def _control_allowance(request, grant, began):
        control = grant.control
        if (
            control.binding != request.binding
            or control.request_digest != backend_operation_request_digest(request)
            or grant.remaining_budget_ms > control.budget.remaining_ms
        ):
            raise ValueError("worker control allowance is invalid")
        remaining = grant.remaining_budget_ms - int((monotonic() - began) * 1000)
        if remaining <= 0:
            raise TimeoutError("worker control allowance expired during delivery")
        return remaining

    @activity.defn(name="raes.indeterminate")
    async def indeterminate(self, payload) -> str:
        reference = self._reference(payload)
        return await self._job(
            self._control_jobs,
            "control",
            self._control_authority.indeterminate,
            reference,
            budget_ms=reference.control_budget_ms,
        )

    def close(self, *, timeout_ms: int = 2000) -> bool:
        from .operation_execution_adapter import require_budget_ms

        deadline = monotonic() + require_budget_ms(timeout_ms) / 1000
        for executor in (self._effect_jobs, self._control_jobs, self._executor):
            if not executor.close(timeout_ms=max(1, int((deadline - monotonic()) * 1000))):
                return False
        return True


def create_temporal_workers(
    client, configuration, activities: TemporalOperationActivities, *, effect_capacity=1, control_capacity=2
):
    from temporalio.worker import Worker

    from .operation_temporal_workflow import RaeOperationWorkflow, RaeSupervisionWorkflow

    if client.namespace != configuration.namespace:
        raise ValueError("Temporal worker namespace does not match configured authority")
    return (
        Worker(
            client, task_queue=configuration.workflow_queue, workflows=[RaeOperationWorkflow, RaeSupervisionWorkflow]
        ),
        Worker(
            client,
            task_queue=configuration.effect_queue,
            activities=[activities.invoke],
            max_concurrent_activities=effect_capacity,
            disable_eager_activity_execution=True,
        ),
        Worker(
            client,
            task_queue=configuration.control_queue,
            activities=[activities.observe, activities.indeterminate, activities.control],
            max_concurrent_activities=control_capacity,
            disable_eager_activity_execution=True,
        ),
    )

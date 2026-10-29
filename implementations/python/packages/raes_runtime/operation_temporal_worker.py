"""Trusted activity workers obtain scoped live grants through the state authority."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import TYPE_CHECKING, Any

import anyio
from pydantic import ValidationError
from raes_contracts.contracts import (
    BackendOperationCapabilitiesModel,
    BackendOperationResponseModel,
    backend_operation_request_digest,
    require_backend_operation_admission,
    validate_backend_operation_response,
)
from raes_contracts.errors import AuthorizationError, ConflictError, InvalidInputError, OperationalError, RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from temporalio import activity

from .errors import RuntimeBudgetExhaustedError
from .operation_control_budget import ControlDeliveryGrant
from .operation_execution_adapter import LocalExecutionAdapter
from .operation_temporal import EngineOperationReference

if TYPE_CHECKING:
    from raes_backend_protocols.operation_supervision import BackendOperationProvider
    from raes_contracts.contracts import BackendOperationRequestModel
    from temporalio.client import Client
    from temporalio.worker import Worker
    from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

    from .operation_execution_adapter import Lane
    from .operation_remote_authority import RemoteOperationAuthority
    from .operation_temporal import TemporalExecutionConfiguration

_LOGGER = get_logger(__name__)


# The SDK decodes raw JSON using these annotations. Carrier models validate
# the wire values immediately afterward; object is not an SDK JSON value type.
class TemporalOperationActivities:
    """Backend integration code only; no ledger credentials or scenario interpreter."""

    def __init__(
        self,
        *,
        provider: BackendOperationProvider,
        effect_authority: RemoteOperationAuthority,
        control_authority: RemoteOperationAuthority,
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

    def _reference(self, payload: dict[str, Any]) -> EngineOperationReference:
        try:
            reference = EngineOperationReference.model_validate(payload)
        except ValidationError:
            # The validation detail can echo payload values; Temporal history records only this message.
            raise InvalidInputError("engine operation reference is invalid") from None
        if reference.worker_id != self._worker_identity:
            raise AuthorizationError("engine reference belongs to another worker")
        return reference

    @staticmethod
    def _request(
        authority: RemoteOperationAuthority, reference: EngineOperationReference
    ) -> BackendOperationRequestModel:
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
            raise ConflictError("engine reference does not match admitted authority")
        return request

    @activity.defn(name="raes.invoke")
    async def invoke(self, payload: dict[str, Any]) -> str:
        reference = self._reference(payload)
        return await self._job(
            self._effect_jobs, "effect", self._invoke, reference, budget_ms=reference.execution_budget_ms
        )

    async def _job[T](
        self, executor: LocalExecutionAdapter, lane: Lane, method: Callable[..., T], *args: object, budget_ms: int
    ) -> T:
        from .operation_execution_adapter import require_budget_ms

        deadline = monotonic() + require_budget_ms(budget_ms) / 1000

        def admitted() -> T:
            remaining = int((deadline - monotonic()) * 1000)
            if remaining <= 0:
                raise RuntimeBudgetExhaustedError("activity allowance exhausted before admission")
            return executor.call(lane, method, *args, timeout_ms=remaining)

        try:
            with anyio.fail_after(budget_ms / 1000):
                return await anyio.to_thread.run_sync(
                    admitted, abandon_on_cancel=True, limiter=self._offload_limiters[lane]
                )
        except Exception as exc:
            # Temporal history records only this fixed failure; keep an unexpected cause in one value-free record.
            if not isinstance(exc, RaesError):
                _LOGGER.exception(
                    "backend activity failed before its outcome was established", exc_info=foreign_failure_record(exc)
                )
        # Raised after the handler, so the fixed failure carries no provider exception as its context.
        raise OperationalError("backend activity could not be established")

    def _invoke(self, reference: EngineOperationReference) -> str:
        authority, provider = self._effect_authority, self._provider
        granted: tuple[BackendOperationRequestModel, int] | None = None
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
                raise InvalidInputError("invocation grant changed its admitted request")
            remaining = grant.remaining_budget_ms - int((monotonic() - grant_started) * 1000)
            if remaining <= 0:
                raise RuntimeBudgetExhaustedError("invocation grant expired in delivery")
            granted = request, remaining
        except Exception as exc:
            # Isolation of the provider and the authority claim: the operation becomes indeterminate.
            if not isinstance(exc, RaesError):
                _LOGGER.exception("backend admission or invocation grant failed", exc_info=foreign_failure_record(exc))
        # Each indeterminate settlement runs after its handler, so a settlement failure carries
        # no provider exception as its context.
        if granted is None:
            return self._control_authority.indeterminate(reference)
        request, remaining = granted
        try:
            response = self._executor.call("effect", provider.start_operation, request, timeout_ms=remaining)
            response = BackendOperationResponseModel.model_validate(response.model_dump(mode="json"))
            validate_backend_operation_response(request, response)
            if response.message.kind != "acknowledgement":
                raise InvalidInputError("backend acknowledgement is invalid")
            return authority.publish(reference, response)
        except Exception as exc:
            if not isinstance(exc, RaesError):
                _LOGGER.exception("backend operation start failed", exc_info=foreign_failure_record(exc))
        return self._control_authority.indeterminate(reference)

    @activity.defn(name="raes.observe")
    async def observe(self, payload: dict[str, Any]) -> str:
        reference = self._reference(payload)
        return await self._job(
            self._control_jobs, "control", self._observe, reference, budget_ms=reference.control_budget_ms
        )

    def _observe(self, reference: EngineOperationReference) -> str:
        authority = self._control_authority
        try:
            request = self._request(authority, reference)
            began = monotonic()
            grant = ControlDeliveryGrant.model_validate(authority.observation(reference))
            control = grant.control
            remaining = self._control_allowance(request, grant, began)
            if control.action != "observe":
                raise InvalidInputError("worker observation grant is invalid")
            response = self._executor.call(
                "control",
                self._provider.observe_operation,
                control,
                timeout_ms=min(remaining, reference.control_budget_ms),
            )
            response = BackendOperationResponseModel.model_validate(response.model_dump(mode="json"))
            validate_backend_operation_response(request, response, control=control)
            if response.message.kind not in {"progress", "outcome", "control", "reconciliation"}:
                raise InvalidInputError("backend observation is invalid")
            return authority.publish(reference, response)
        except Exception as exc:
            # Isolation of the provider observation: the operation becomes indeterminate.
            if not isinstance(exc, RaesError):
                _LOGGER.exception("backend operation observation failed", exc_info=foreign_failure_record(exc))
        # Settled after the handler, so a settlement failure carries no provider exception as its context.
        return authority.indeterminate(reference)

    @activity.defn(name="raes.control")
    async def control(self, payload: dict[str, Any]) -> str:
        reference = self._reference(payload["reference"])
        from pydantic import TypeAdapter
        from raes_contracts.contracts.backend_operation import OperationIdentifier

        control_id = TypeAdapter(OperationIdentifier).validate_python(payload["control_id"])
        return await self._job(
            self._control_jobs, "control", self._control, reference, control_id, budget_ms=reference.control_budget_ms
        )

    def _control(self, reference: EngineOperationReference, control_id: str) -> str:
        authority = self._control_authority
        request = self._request(authority, reference)
        # Redelivery cannot reacquire a consumed control claim either.
        began = monotonic()
        grant = ControlDeliveryGrant.model_validate(authority.get_control(reference, control_id))
        control = grant.control
        remaining = self._control_allowance(request, grant, began)
        if control.control_id != control_id:
            raise InvalidInputError("worker control grant is invalid")
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
            raise InvalidInputError("backend control response is invalid")
        return authority.publish(reference, response)

    @staticmethod
    def _control_allowance(request: BackendOperationRequestModel, grant: ControlDeliveryGrant, began: float) -> int:
        control = grant.control
        if (
            control.binding != request.binding
            or control.request_digest != backend_operation_request_digest(request)
            or grant.remaining_budget_ms > control.budget.remaining_ms
        ):
            raise InvalidInputError("worker control allowance is invalid")
        remaining = grant.remaining_budget_ms - int((monotonic() - began) * 1000)
        if remaining <= 0:
            raise RuntimeBudgetExhaustedError("worker control allowance expired during delivery")
        return remaining

    @activity.defn(name="raes.indeterminate")
    async def indeterminate(self, payload: dict[str, Any]) -> str:
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


def workflow_sandbox_runner() -> SandboxedWorkflowRunner:
    """Return the SDK sandbox with coverage measurement passed through.

    Coverage's `sys.monitoring` core imports its own modules lazily from
    callbacks that run inside workflow code. The sandbox would load those
    modules again under its restrictions and fail the workflow task. The SDK
    passes Pydantic through for the same lazy-import reason. Coverage does not
    affect workflow determinism, and the other default restrictions stay.
    """

    from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

    return SandboxedWorkflowRunner(restrictions=SandboxRestrictions.default.with_passthrough_modules("coverage"))


def create_temporal_workers(
    client: Client,
    configuration: TemporalExecutionConfiguration,
    activities: TemporalOperationActivities,
    *,
    effect_capacity: int = 1,
    control_capacity: int = 2,
) -> tuple[Worker, Worker, Worker]:
    from temporalio.worker import Worker

    from .operation_temporal_workflow import RaeOperationWorkflow, RaeSupervisionWorkflow

    if client.namespace != configuration.namespace:
        raise ValueError("Temporal worker namespace does not match configured authority")
    return (
        Worker(
            client,
            task_queue=configuration.workflow_queue,
            workflows=[RaeOperationWorkflow, RaeSupervisionWorkflow],
            workflow_runner=workflow_sandbox_runner(),
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

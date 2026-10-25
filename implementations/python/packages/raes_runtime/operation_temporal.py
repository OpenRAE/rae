"""Optional Temporal delivery: stable references, independent queues, no effect retries."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Annotated, Literal

import anyio
from anyio.from_thread import start_blocking_portal
from pydantic import ConfigDict, Field
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendOperationRequestModel, backend_operation_request_digest
from raes_contracts.contracts.backend_operation import (
    OperationCounter,
    OperationDigest,
    OperationIdentifier,
    OperationPositive,
)
from raes_contracts.contracts.base import ContractModel

from .operation_execution_adapter import require_budget_ms

if TYPE_CHECKING:
    from raes_contracts.contracts import BackendOperationControlModel
    from temporalio.client import Client


class EngineOperationReference(ContractModel):
    """Private, versioned adapter payload: no plan, credential or live resolver."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["raes-engine-operation/v1"] = "raes-engine-operation/v1"
    operation_id: OperationIdentifier
    invocation_id: OperationIdentifier
    deployment_id: OperationIdentifier
    owner_generation: OperationCounter
    execution_generation: OperationCounter
    worker_id: OperationIdentifier
    request_digest: OperationDigest
    effect_queue: Annotated[str, Field(min_length=1, max_length=128)]
    control_queue: Annotated[str, Field(min_length=1, max_length=128)]
    execution_budget_ms: OperationPositive
    control_budget_ms: OperationPositive

    def require_request(self, request: BackendOperationRequestModel) -> None:
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
            self.operation_id,
            self.invocation_id,
            self.deployment_id,
            self.owner_generation,
            self.execution_generation,
            self.worker_id,
            self.request_digest,
        ):
            raise ValueError("engine reference does not match admitted authority")


class EngineDeliveryBinding(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    namespace: OperationIdentifier
    workflow_queue: OperationIdentifier
    workflow_id: OperationIdentifier
    reference: EngineOperationReference


@dataclass(frozen=True, kw_only=True)
class TemporalExecutionConfiguration:
    namespace: str = "default"
    workflow_queue: str = "raes.operations"
    effect_queue: str = "raes.effects"
    control_queue: str = "raes.control"
    worker_identity: str = "rae-effect-worker"
    rpc_budget_ms: int = 2000

    def __post_init__(self) -> None:
        for value in (self.namespace, self.workflow_queue, self.effect_queue, self.control_queue, self.worker_identity):
            if (
                not isinstance(value, str)
                or not 1 <= len(value) <= 128
                or any(c.isspace() or ord(c) < 32 for c in value)
            ):
                raise ValueError("Temporal names must be bounded configured identifiers")
        if len({self.workflow_queue, self.effect_queue, self.control_queue}) != 3:
            raise ValueError("Temporal workflow, effect and control queues must be distinct")
        require_budget_ms(self.rpc_budget_ms)


class TemporalExecutionAdapter:
    """A client factory connects on its owning loop, only when delivery is used.

    The host owns approved endpoints, mTLS/authorization, and service lifecycle.
    Start retries reuse this exact identity. Duplicate engine execution still
    needs the state authority's current one-use invocation grant.
    """

    def __init__(
        self, configuration: TemporalExecutionConfiguration, *, client_factory: Callable[[], Awaitable[Client]]
    ) -> None:
        if not isinstance(configuration, TemporalExecutionConfiguration) or not callable(client_factory):
            raise TypeError("Temporal execution requires typed settings and a configured client factory")
        self.configuration = configuration
        self._factory = client_factory
        self._client = None
        self._portal_context = start_blocking_portal(name="runtime-temporal")
        self._portal = self._portal_context.__enter__()
        self._closed = False

    @property
    def worker_identity(self) -> str:
        return self.configuration.worker_identity

    def reference(self, request: BackendOperationRequestModel) -> EngineOperationReference:
        if request.binding.worker_id != self.worker_identity:
            raise ValueError("Temporal worker does not match the admitted invocation")
        binding = request.binding
        return EngineOperationReference(
            operation_id=binding.operation_id,
            invocation_id=binding.invocation_id,
            deployment_id=binding.deployment_id,
            owner_generation=binding.owner_generation,
            execution_generation=binding.execution_generation,
            worker_id=binding.worker_id,
            request_digest=backend_operation_request_digest(request),
            effect_queue=self.configuration.effect_queue,
            control_queue=self.configuration.control_queue,
            execution_budget_ms=request.budget.remaining_ms,
            control_budget_ms=self.configuration.rpc_budget_ms,
        )

    def submit(self, request: BackendOperationRequestModel) -> str:
        if self._closed:
            raise RuntimeError("Temporal execution adapter is closed")
        delivery = self.binding(request)
        self._portal.call(self._start, delivery.reference, delivery.workflow_id)
        return delivery.workflow_id

    def binding(self, request: BackendOperationRequestModel) -> EngineDeliveryBinding:
        reference = self.reference(request)
        workflow_id = "raes-operation-" + canonical_json_digest(
            {
                "binding": request.binding.model_dump(mode="json"),
                "request_digest": reference.request_digest,
            }
        ).removeprefix("sha256:")
        return EngineDeliveryBinding(
            namespace=self.configuration.namespace,
            workflow_queue=self.configuration.workflow_queue,
            workflow_id=workflow_id,
            reference=reference,
        )

    def deliver_control(self, request: BackendOperationRequestModel, control: BackendOperationControlModel) -> None:
        delivery = self.binding(request)
        self._portal.call(self._control, delivery.reference, control.control_id)

    async def _control(self, reference: EngineOperationReference, control_id: str) -> None:
        from temporalio.common import RetryPolicy, WorkflowIDConflictPolicy, WorkflowIDReusePolicy
        from temporalio.exceptions import WorkflowAlreadyStartedError

        client = await self._connected()
        payload = {"reference": reference.model_dump(mode="json"), "control_id": control_id}
        workflow_id = "raes-control-" + canonical_json_digest(payload).removeprefix("sha256:")
        with anyio.fail_after(self.configuration.rpc_budget_ms / 1000):
            try:
                await client.start_workflow(
                    "raes.supervision",
                    payload,
                    id=workflow_id,
                    task_queue=self.configuration.workflow_queue,
                    execution_timeout=timedelta(milliseconds=3 * reference.control_budget_ms),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                    id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
                    rpc_timeout=timedelta(milliseconds=self.configuration.rpc_budget_ms),
                )
            except WorkflowAlreadyStartedError:
                retained = await client.get_workflow_handle(workflow_id).query(
                    "control_reference", rpc_timeout=timedelta(milliseconds=self.configuration.rpc_budget_ms)
                )
                if retained != payload:
                    raise ValueError("Temporal control binding conflict") from None

    async def _connected(self) -> Client:
        if self._client is None:
            with anyio.fail_after(self.configuration.rpc_budget_ms / 1000):
                self._client = await self._factory()
            if self._client.namespace != self.configuration.namespace:
                self._client = None
                raise ValueError("Temporal client namespace does not match configuration")
        return self._client

    async def _start(self, reference: EngineOperationReference, workflow_id: str) -> None:
        from temporalio.common import RetryPolicy, WorkflowIDConflictPolicy, WorkflowIDReusePolicy
        from temporalio.exceptions import WorkflowAlreadyStartedError

        client = await self._connected()
        payload = reference.model_dump(mode="json")
        with anyio.fail_after(self.configuration.rpc_budget_ms / 1000):
            try:
                await client.start_workflow(
                    "raes.operation",
                    payload,
                    id=workflow_id,
                    task_queue=self.configuration.workflow_queue,
                    execution_timeout=timedelta(
                        milliseconds=reference.execution_budget_ms + 3 * reference.control_budget_ms
                    ),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                    id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
                    rpc_timeout=timedelta(milliseconds=self.configuration.rpc_budget_ms),
                )
            except WorkflowAlreadyStartedError:
                handle = client.get_workflow_handle(workflow_id)
                retained = await handle.query(
                    "operation_reference", rpc_timeout=timedelta(milliseconds=self.configuration.rpc_budget_ms)
                )
                if EngineOperationReference.model_validate(retained) != reference:
                    raise ValueError("Temporal execution binding conflict") from None

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._portal_context.__exit__(None, None, None)


__all__ = ("EngineOperationReference", "TemporalExecutionAdapter", "TemporalExecutionConfiguration")

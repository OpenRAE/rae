"""Stable run/sequence workflow starts through the existing Temporal client."""

from datetime import timedelta

import anyio

from .runtime_sequence_reference import RuntimeSequenceReference


async def start_runtime_workflow(adapter, reference):
    from temporalio.common import RetryPolicy, WorkflowIDConflictPolicy, WorkflowIDReusePolicy
    from temporalio.exceptions import WorkflowAlreadyStartedError

    reference = RuntimeSequenceReference.model_validate(reference.model_dump(mode="json"))
    client = await adapter._connected()
    with anyio.fail_after(adapter.configuration.rpc_budget_ms / 1000):
        try:
            await client.start_workflow(
                "raes." + reference.kind,
                reference.model_dump(mode="json"),
                id=reference.workflow_id,
                task_queue=adapter.configuration.workflow_queue,
                retry_policy=RetryPolicy(maximum_attempts=1),
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
                rpc_timeout=timedelta(milliseconds=adapter.configuration.rpc_budget_ms),
            )
        except WorkflowAlreadyStartedError:
            retained = await client.get_workflow_handle(reference.workflow_id).query(
                "runtime_reference", rpc_timeout=timedelta(milliseconds=adapter.configuration.rpc_budget_ms)
            )
            if RuntimeSequenceReference.model_validate(retained) != reference:
                raise ValueError("Temporal runtime binding conflict") from None
    return reference.workflow_id

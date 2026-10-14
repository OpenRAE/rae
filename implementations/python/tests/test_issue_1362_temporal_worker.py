"""A redelivered effect activity has to pass the live owner gate again."""

import asyncio

import pytest
from raes_contracts.contracts import backend_operation_request_digest
from test_issue_1360_backend_operations import capabilities, control, request, response
from test_issue_1362_provider_execution import Provider


def test_redelivered_activity_never_repeats_a_consumed_effect():
    from raes_runtime.operation_temporal import EngineOperationReference
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities
    from raes_runtime.operation_worker_authority import InvocationGrant

    operation = request()
    provider = Provider()
    provider.operation_capabilities = capabilities
    provider.report = lambda request, message: response(message, sequence=1, operation=request)

    class Authority:
        consumed = False
        reports = []

        def get_request(self, reference):
            return operation

        def claim(self, reference, capabilities, admission):
            if self.consumed:
                raise ValueError("grant already consumed")
            self.consumed = True
            return InvocationGrant(request=operation, remaining_budget_ms=100)

        def publish(self, reference, response):
            self.reports.append(response)
            return "running"

        def indeterminate(self, reference):
            return "indeterminate"

    reference = EngineOperationReference(
        operation_id=operation.binding.operation_id,
        invocation_id=operation.binding.invocation_id,
        deployment_id=operation.binding.deployment_id,
        owner_generation=operation.binding.owner_generation,
        execution_generation=operation.binding.execution_generation,
        worker_id=operation.binding.worker_id,
        request_digest=backend_operation_request_digest(operation),
        effect_queue="effects",
        control_queue="controls",
        execution_budget_ms=100,
        control_budget_ms=100,
    )
    authority = Authority()
    activities = TemporalOperationActivities(
        provider=provider, effect_authority=authority, control_authority=authority, worker_identity="worker-1"
    )

    async def exercise():
        await activities.invoke(reference.model_dump(mode="json"))
        await activities.invoke(reference.model_dump(mode="json"))

    try:
        asyncio.run(exercise())
        assert provider.starts == 1
        assert authority.consumed
    finally:
        assert activities.close()


def test_foreign_engine_reference_cannot_select_a_different_worker_or_obtain_a_grant():
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities

    class Authority:
        def get_request(self, reference):
            pytest.fail("foreign activity obtained worker authority")

    activities = TemporalOperationActivities(
        provider=Provider(), effect_authority=Authority(), control_authority=Authority(), worker_identity="worker-1"
    )
    try:
        rejected_invocation = activities.invoke({"worker_id": "another-worker"})
        with pytest.raises(ValueError):
            asyncio.run(rejected_invocation)
    finally:
        assert activities.close()


def test_native_control_exception_is_not_serialized_into_engine_history():
    from raes_runtime.operation_temporal import EngineOperationReference
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities

    operation = request()

    class Authority:
        def get_request(self, reference):
            return operation

        def get_control(self, reference, control_id):
            from raes_runtime.operation_control_budget import ControlDeliveryGrant

            return ControlDeliveryGrant(control=control(), remaining_budget_ms=900)

    provider = Provider()

    def broken(control):
        raise RuntimeError("sensitive-provider-value")

    provider.cancel_operation = broken
    reference = EngineOperationReference(
        operation_id=operation.binding.operation_id,
        invocation_id=operation.binding.invocation_id,
        deployment_id=operation.binding.deployment_id,
        owner_generation=operation.binding.owner_generation,
        execution_generation=operation.binding.execution_generation,
        worker_id=operation.binding.worker_id,
        request_digest=backend_operation_request_digest(operation),
        effect_queue="effect",
        control_queue="control",
        execution_budget_ms=1000,
        control_budget_ms=1000,
    )
    authority = Authority()
    activities = TemporalOperationActivities(
        provider=provider, effect_authority=authority, control_authority=authority, worker_identity="worker-1"
    )
    try:
        rejected_payload = reference.model_dump(mode="json")
        rejected_control = activities.control({"reference": rejected_payload, "control_id": "control-1"})
        with pytest.raises(RuntimeError) as rejected:
            asyncio.run(rejected_control)
        assert "sensitive-provider-value" not in str(rejected.value)
        assert rejected.value.__suppress_context__
    finally:
        assert activities.close()


def test_installed_workflows_are_accepted_by_the_real_sdk_sandbox():
    from raes_runtime.operation_temporal_workflow import RaeOperationWorkflow, RaeSupervisionWorkflow
    from temporalio import workflow
    from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

    async def exercise():
        for definition in (RaeOperationWorkflow, RaeSupervisionWorkflow):
            SandboxedWorkflowRunner().prepare_workflow(workflow._Definition.must_from_class(definition))

    asyncio.run(exercise())

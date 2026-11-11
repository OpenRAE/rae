"""A redelivered effect activity has to pass the live owner gate again."""

import asyncio

import pytest
from raes_contracts.contracts import backend_operation_request_digest
from raes_contracts.errors import InvalidInputError, OperationalError
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
        with pytest.raises(InvalidInputError):
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
        with pytest.raises(OperationalError) as rejected:
            asyncio.run(rejected_control)
        assert "sensitive-provider-value" not in str(rejected.value)
        # No provider exception in the chain, not even as a suppressed context.
        assert (rejected.value.__cause__, rejected.value.__context__) == (None, None)
    finally:
        assert activities.close()


def test_installed_workflows_are_accepted_by_the_real_sdk_sandbox():
    from raes_runtime.operation_temporal_worker import workflow_sandbox_runner
    from raes_runtime.operation_temporal_workflow import RaeOperationWorkflow, RaeSupervisionWorkflow
    from temporalio import workflow

    async def exercise():
        for definition in (RaeOperationWorkflow, RaeSupervisionWorkflow):
            workflow_sandbox_runner().prepare_workflow(workflow._Definition.must_from_class(definition))

    asyncio.run(exercise())


def test_workflow_sandbox_passes_only_coverage_through_beyond_the_sdk_defaults():
    from raes_runtime.operation_temporal_worker import workflow_sandbox_runner
    from temporalio.worker.workflow_sandbox import SandboxRestrictions

    restrictions = workflow_sandbox_runner().restrictions
    default = SandboxRestrictions.default
    assert restrictions.passthrough_modules == default.passthrough_modules | {"coverage"}
    assert restrictions.invalid_modules == default.invalid_modules
    assert restrictions.invalid_module_members == default.invalid_module_members


@pytest.mark.parametrize("entrypoint", ["operation", "supervision", "invoke", "observe", "control", "indeterminate"])
def test_sdk_decodes_opaque_payload_using_registered_entrypoint_annotations(entrypoint):
    from typing import get_type_hints

    from raes_runtime.operation_temporal_worker import TemporalOperationActivities
    from raes_runtime.operation_temporal_workflow import RaeOperationWorkflow, RaeSupervisionWorkflow
    from temporalio.converter import JSONPlainPayloadConverter

    if entrypoint == "operation":
        method = RaeOperationWorkflow.run
    elif entrypoint == "supervision":
        method = RaeSupervisionWorkflow.run
    else:
        method = getattr(TemporalOperationActivities, entrypoint)
    reference = {
        "operation_id": "sdk-wire-operation",
        "owner_generation": 1,
        "execution_generation": 2,
        "control_budget_ms": 1000,
    }
    payload = (
        {"reference": reference, "control_id": "sdk-wire-control"}
        if entrypoint in {"supervision", "control"}
        else reference
    )
    converter = JSONPlainPayloadConverter()
    encoded = converter.to_payload(payload)
    decoded = converter.from_payload(encoded, get_type_hints(method)["payload"])
    assert decoded == payload


def test_timed_out_activity_keeps_its_slot_until_the_callback_settles():
    from threading import Event
    from time import monotonic

    from raes_runtime.operation_temporal_worker import TemporalOperationActivities

    held, release = Event(), Event()
    calls = []
    activities = TemporalOperationActivities(
        provider=Provider(), effect_authority=None, control_authority=None, worker_identity="worker-1"
    )

    def blocked():
        held.set()
        assert release.wait(3)

    async def exercise():
        first = asyncio.create_task(activities._job(activities._effect_jobs, "effect", blocked, budget_ms=50))
        assert await asyncio.to_thread(held.wait, 1)
        with pytest.raises(OperationalError):
            await first
        assert activities._effect_jobs.pending_calls == 1
        with pytest.raises(OperationalError):
            await activities._job(activities._effect_jobs, "effect", lambda: calls.append("premature"), budget_ms=100)
        assert calls == []
        release.set()
        deadline = monotonic() + 1
        while activities._effect_jobs.pending_calls:
            assert monotonic() < deadline
            await asyncio.sleep(0.01)
        await activities._job(activities._effect_jobs, "effect", lambda: calls.append("settled"), budget_ms=100)
        assert calls == ["settled"]

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        assert activities.close()

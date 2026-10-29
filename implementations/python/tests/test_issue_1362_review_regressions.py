"""Regression witnesses for the recorded execution review findings."""

import asyncio
from threading import Event, Thread

import pytest
from raes_contracts.errors import OperationalError
from raes_contracts.operation_lifecycle import OperationKind
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_mutation import RuntimeMutationAuthority
from raes_runtime.errors import RuntimeBudgetExhaustedError
from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration
from test_issue_1362_distributed_authority import Dispatcher, worker
from test_issue_1362_provider_execution import Evidence, Provider, target
from test_issue_1362_runtime_supervision import supervisor


@pytest.mark.parametrize("asynchronous", [False, True])
def test_failed_reacquisition_does_not_grant_a_second_writer(asynchronous):
    authority = RuntimeMutationAuthority(admission_ms=1000)
    external, finish_external, supervisor_entered, release_supervisor = Event(), Event(), Event(), Event()
    reacquiring, effect_unwound, queued_entered = Event(), Event(), Event()
    original_wait = authority._condition.wait_for

    def bounded_reacquisition(predicate, timeout=None):
        if getattr(predicate, "__name__", "") == "_permit_is_free":
            reacquiring.set()
            return original_wait(predicate, timeout=0.08)
        return original_wait(predicate, timeout=timeout)

    authority._condition.wait_for = bounded_reacquisition

    def outside():
        with authority.external_call():
            external.set()
            assert finish_external.wait(3)

    def effect():
        try:
            if asynchronous:

                async def reserved():
                    async with authority.reserve(OperationKind.PROVISIONING):
                        await asyncio.to_thread(outside)

                asyncio.run(reserved())
            else:
                with authority.mutation(OperationKind.PROVISIONING):
                    outside()
        except RuntimeBudgetExhaustedError:
            effect_unwound.set()

    def supervise():
        with authority.supervision():
            supervisor_entered.set()
            assert release_supervisor.wait(3)

    effect_thread, control_thread = Thread(target=effect), Thread(target=supervise)
    effect_thread.start()
    assert external.wait(1)
    control_thread.start()
    assert supervisor_entered.wait(1)
    finish_external.set()
    assert reacquiring.wait(1)

    async def exercise():
        async def queued():
            async with authority.reserve(OperationKind.PROVISIONING):
                queued_entered.set()

        task = asyncio.create_task(queued())
        try:
            assert await asyncio.to_thread(effect_unwound.wait, 1)
            assert not await asyncio.to_thread(queued_entered.wait, 0.04)
        finally:
            release_supervisor.set()
            await task

    try:
        asyncio.run(exercise())
    finally:
        finish_external.set()
        release_supervisor.set()
        effect_thread.join(2)
        control_thread.join(2)
    assert queued_entered.is_set()


def test_deadline_classification_can_use_the_single_store_slot():
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(
        target(provider),
        operation_evidence=Evidence(),
        distributed_execution=dispatcher,
        supervision=OperationSupervisionConfiguration(execution_ms=200, store_capacity=1),
    )
    expired, failures = Event(), []
    original = plane._expire_backend_invocation

    def expiry(binding):
        try:
            original(binding)
        except Exception as error:
            failures.append(type(error))
            raise
        finally:
            expired.set()

    plane._expire_backend_invocation = expiry
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        assert expired.wait(1)
        assert not failures
        assert plane._store.raw_store.load_records()[receipt.operation_id].status.state is OperationState.CANCELLED
        assert receipt.operation_id not in plane._admitted_backend_requests
        assert receipt.operation_id not in plane._execution_deadlines
    finally:
        plane.close()


def test_failed_deadline_classification_closes_runtime_authority():
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(
        target(provider),
        operation_evidence=Evidence(),
        distributed_execution=dispatcher,
        supervision=OperationSupervisionConfiguration(execution_ms=100),
    )
    poisoned = Event()
    original = plane._poison_runtime_durability

    def poison():
        original()
        poisoned.set()

    def fail(binding):
        raise RuntimeError("classification unavailable")

    plane._poison_runtime_durability = poison
    plane._expire_backend_invocation = fail
    try:
        plane.submit_provisioning(ProvisioningPlan())
        assert poisoned.wait(1)
        assert plane._durability_poisoned
        rejected_plan = ProvisioningPlan()
        with pytest.raises(OperationalError):
            plane.submit_provisioning(rejected_plan)
    finally:
        plane.close()


@pytest.mark.parametrize("cancelled", [False, True])
def test_confirmed_terminal_cut_releases_transient_dispatch_context(cancelled):
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence(), distributed_execution=dispatcher)
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        request = dispatcher.commands[0]
        assert receipt.operation_id in plane._admitted_backend_requests
        if cancelled:
            plane.cancel_operation(receipt.operation_id, control_id="cancel-review", identity=supervisor())
        else:
            plane.claim_backend_invocation(
                request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
            )
            plane.publish_backend_response(provider.start_operation(request), identity=worker())
            # The no-op provider's outcome does not require a control disposition.
            response = provider.observe_operation(None)
            plane.publish_backend_response(response, identity=worker())
        assert receipt.operation_id not in plane._admitted_backend_requests
        assert receipt.operation_id not in plane._execution_deadlines
        assert plane._store.load_records()[receipt.operation_id].invocation is not None
    finally:
        plane.close()


@pytest.mark.parametrize("blocked_method", ["operation_capabilities", "check_operation"])
@pytest.mark.parametrize("outer_capacity", [None, 1])
def test_blocked_worker_admission_leaves_the_single_control_slot_available(blocked_method, outer_capacity):
    from raes_contracts.contracts import backend_operation_request_digest
    from raes_runtime.operation_temporal import EngineOperationReference
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities
    from raes_runtime.operation_worker_authority import InvocationGrant
    from test_issue_1360_backend_operations import capabilities, control, request, response

    operation = request()
    entered, release = Event(), Event()
    provider = Provider()
    provider.request = operation
    provider.operation_capabilities = capabilities
    provider.report = lambda request, message: response(message, operation=request)
    original = getattr(provider, blocked_method)

    def block(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    setattr(provider, blocked_method, block)

    class Authority:
        reports = []

        def get_request(self, reference):
            return operation

        def claim(self, *args):
            return InvocationGrant(request=operation, remaining_budget_ms=1000)

        def get_control(self, *args):
            from raes_runtime.operation_control_budget import ControlDeliveryGrant

            return ControlDeliveryGrant(control=control(), remaining_budget_ms=900)

        def publish(self, reference, result):
            self.reports.append(result)
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
        effect_queue="effect",
        control_queue="control",
        execution_budget_ms=1000,
        control_budget_ms=1000,
    )
    authority = Authority()
    activities = TemporalOperationActivities(
        provider=provider,
        effect_authority=authority,
        control_authority=authority,
        worker_identity="worker-1",
        control_capacity=1,
    )

    async def exercise():
        import anyio

        limiter = anyio.to_thread.current_default_thread_limiter()
        previous = limiter.total_tokens
        if outer_capacity is not None:
            limiter.total_tokens = outer_capacity
        invocation = asyncio.create_task(activities.invoke(reference.model_dump(mode="json")))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            await asyncio.wait_for(
                activities.control({"reference": reference.model_dump(mode="json"), "control_id": "control-1"}), 0.3
            )
            assert provider.cancels == 1
            assert authority.reports[0].message.disposition == "accepted"
        finally:
            release.set()
            await invocation
            limiter.total_tokens = previous

    try:
        asyncio.run(exercise())
    finally:
        release.set()
        assert activities.close()


@pytest.mark.parametrize("blocked_method", ["operation_capabilities", "check_operation"])
def test_blocked_local_admission_leaves_distributed_control_delivery_available(blocked_method):
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(
        target(provider),
        operation_evidence=Evidence(),
        distributed_execution=dispatcher,
        supervision=OperationSupervisionConfiguration(control_capacity=1),
    )
    entered, release, delivered = Event(), Event(), Event()
    original = getattr(provider, blocked_method)

    def block(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    dispatcher.deliver_control = lambda request, control: delivered.set()
    second = None
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        request = dispatcher.commands[0]
        plane.claim_backend_invocation(
            request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
        )
        setattr(provider, blocked_method, block)
        second = Thread(target=lambda: plane.submit_provisioning(ProvisioningPlan()))
        second.start()
        assert entered.wait(1)
        plane.cancel_operation(receipt.operation_id, control_id="independent-local", identity=supervisor())
        assert delivered.is_set()
    finally:
        release.set()
        if second is not None:
            second.join(2)
        plane.close()

"""Engine delivery and scoped service identity never recreate effect authority."""

import pytest
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from test_issue_1362_provider_execution import Evidence, Provider, target


class Dispatcher:
    worker_identity = "worker-1362"

    def __init__(self):
        self.commands = []

    def submit(self, request):
        self.commands.append(request)
        return self.binding(request).workflow_id

    def close(self):
        pass

    def binding(self, request):
        from raes_runtime.operation_temporal import TemporalExecutionAdapter, TemporalExecutionConfiguration

        adapter = object.__new__(TemporalExecutionAdapter)
        adapter.configuration = TemporalExecutionConfiguration(worker_identity=self.worker_identity)
        return adapter.binding(request)

    def deliver_control(self, request, control):
        pass


def worker(name="worker-1362"):
    return ControlPlaneIdentity(identity=name, roles=frozenset({ControlPlaneRole.BACKEND}), target_name="stub")


def test_distributed_delivery_requires_a_current_confirmed_grant_and_cannot_claim_it_twice():
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence(), distributed_execution=dispatcher)
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        assert plane.get_operation(receipt.operation_id).state is OperationState.ACCEPTED
        assert provider.starts == 0
        request = dispatcher.commands[0]
        admission = provider.check_operation(request)
        rejected_capabilities = provider.operation_capabilities()
        rejected_identity = worker("foreign-worker")
        with pytest.raises(PermissionError):
            plane.claim_backend_invocation(
                request.binding, rejected_capabilities, admission, identity=rejected_identity
            )
        assert not plane._store.load_records()[receipt.operation_id].invocation.consumed
        grant = plane.claim_backend_invocation(
            request.binding, provider.operation_capabilities(), admission, identity=worker()
        )
        assert grant.request == request
        assert grant.remaining_budget_ms <= request.budget.remaining_ms
        assert plane.get_operation(receipt.operation_id).state is OperationState.RUNNING
        rejected_capabilities_1 = provider.operation_capabilities()
        rejected_identity_1 = worker()
        with pytest.raises(ValueError):
            plane.claim_backend_invocation(
                request.binding, rejected_capabilities_1, admission, identity=rejected_identity_1
            )
        assert provider.starts == 0
    finally:
        plane.close()


def test_owner_replacement_or_missing_clock_continuity_cannot_authorize_dispatch():
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence(), distributed_execution=dispatcher)
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        request = dispatcher.commands[0]
        plane._execution_generation += 1
        rejected_capabilities_2 = provider.operation_capabilities()
        rejected_admission = provider.check_operation(request)
        rejected_identity_2 = worker()
        with pytest.raises((RuntimeError, ValueError)):
            plane.claim_backend_invocation(
                request.binding, rejected_capabilities_2, rejected_admission, identity=rejected_identity_2
            )
        assert plane.get_operation(receipt.operation_id).state is OperationState.ACCEPTED
        assert not plane._store.load_records()[receipt.operation_id].invocation.consumed
    finally:
        plane._execution_generation -= 1
        plane.close()

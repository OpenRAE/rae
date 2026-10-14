"""Control delivery uses one original allowance across queueing and reopening."""

from datetime import UTC, datetime, timedelta
from time import monotonic

import pytest
from raes_contracts.contracts import BackendOperationControlModel, backend_operation_request_digest
from raes_contracts.planning import ProvisioningPlan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from test_issue_1362_distributed_authority import Dispatcher, worker
from test_issue_1362_provider_execution import Evidence, Provider, target
from test_issue_1362_runtime_supervision import supervisor


def test_a_delayed_control_claim_refuses_expiry_before_consuming_delivery(monkeypatch):
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(target(provider), distributed_execution=dispatcher, operation_evidence=Evidence())
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        request = dispatcher.commands[0]
        plane.claim_backend_invocation(
            request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
        )
        control = plane.cancel_operation(receipt.operation_id, control_id="delayed", identity=supervisor())
        future = monotonic() + 10
        monkeypatch.setattr("raes_runtime.operation_control_budget.monotonic", lambda: future)
        with pytest.raises((ValueError, TimeoutError)):
            plane.claim_worker_control(receipt.operation_id, control.control_id, identity=worker())
        assert control.control_id not in plane._store.load_records()[receipt.operation_id].invocation.delivered_controls
    finally:
        plane.close()


def test_reopened_control_has_no_dispatch_clock_continuity(tmp_path):
    provider, dispatcher = Provider(), Dispatcher()
    configured = target(provider)
    plane = RuntimeControlPlane(
        configured,
        store=LocalControlPlaneStore(tmp_path / "ledger"),
        distributed_execution=dispatcher,
        operation_evidence=Evidence(),
    )
    receipt = plane.submit_provisioning(ProvisioningPlan())
    request = dispatcher.commands[0]
    plane.claim_backend_invocation(
        request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
    )
    control = plane.cancel_operation(receipt.operation_id, control_id="retained", identity=supervisor())
    plane.close()
    plane = RuntimeControlPlane(
        configured,
        store=LocalControlPlaneStore(tmp_path / "ledger"),
        distributed_execution=Dispatcher(),
        operation_evidence=Evidence(),
    )
    try:
        with pytest.raises((ValueError, TimeoutError)):
            plane.claim_worker_control(receipt.operation_id, control.control_id, identity=worker())
        assert control.control_id not in plane._store.load_records()[receipt.operation_id].invocation.delivered_controls
    finally:
        plane.close()


def test_worker_observation_returns_a_remaining_grant_without_changing_the_control():
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(target(provider), distributed_execution=dispatcher, operation_evidence=Evidence())
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        request = dispatcher.commands[0]
        control = BackendOperationControlModel(
            binding=request.binding,
            request_digest=backend_operation_request_digest(request),
            control_id="observer",
            actor_id=worker().identity,
            authorization_scope=("role:backend",),
            action="observe",
            budget={
                "origin_id": "original",
                "started_at": (datetime.now(UTC) - timedelta(milliseconds=200)).isoformat(),
                "limit_ms": 1000,
                "remaining_ms": 1000,
            },
        )
        grant = plane.record_worker_observation(control, identity=worker())
        assert grant.control == control
        assert 0 < grant.remaining_budget_ms < 800
        with pytest.raises(ValueError):
            plane.record_worker_observation(control, identity=worker())
    finally:
        plane.close()


def test_local_delivery_counts_the_time_spent_committing_its_claim(monkeypatch):
    import raes_runtime.operation_provider_control as delivery

    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(target(provider), distributed_execution=dispatcher, operation_evidence=Evidence())
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        request = dispatcher.commands[0]
        plane.claim_backend_invocation(
            request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
        )
        control = plane.cancel_operation(receipt.operation_id, control_id="local-delay", identity=supervisor())
        now = [monotonic()]
        monkeypatch.setattr("raes_runtime.operation_control_budget.monotonic", lambda: now[0])
        original = delivery.persist_invocation_update

        def slow_commit(*args, **kwargs):
            committed = original(*args, **kwargs)
            now[0] += 10
            return committed

        monkeypatch.setattr(delivery, "persist_invocation_update", slow_commit)
        with plane._mutation_authority.supervision():
            delivery.deliver_control(plane, plane._store.load_records()[receipt.operation_id], control)
        assert provider.cancels == 0
        assert control.control_id in plane._store.load_records()[receipt.operation_id].invocation.delivered_controls
    finally:
        plane.close()


@pytest.mark.parametrize("action", ["cancel", "observe"])
def test_worker_refuses_a_control_grant_exhausted_during_rpc_delivery(monkeypatch, action):
    from raes_runtime.operation_control_budget import ControlDeliveryGrant
    from raes_runtime.operation_temporal import EngineOperationReference
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities
    from test_issue_1360_backend_operations import control, request

    operation = request()
    provider = Provider()
    calls, now = [], [monotonic()]
    monkeypatch.setattr("raes_runtime.operation_temporal_worker.monotonic", lambda: now[0])

    def late_grant(*args):
        now[0] += 1
        return ControlDeliveryGrant(control=control(action), remaining_budget_ms=100)

    class Authority:
        get_control = staticmethod(late_grant)
        observation = staticmethod(late_grant)

        def get_request(self, reference):
            return operation

        def indeterminate(self, reference):
            return "indeterminate"

    provider.cancel_operation = provider.observe_operation = lambda control: calls.append(control)
    authority = Authority()
    activities = TemporalOperationActivities(
        provider=provider, effect_authority=authority, control_authority=authority, worker_identity="worker-1"
    )
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
    try:
        if action == "cancel":
            with pytest.raises(TimeoutError):
                activities._control(reference, "control-1")
        else:
            assert activities._observe(reference) == "indeterminate"
        assert not calls
    finally:
        assert activities.close()


def test_expired_observation_is_not_recorded_or_granted():
    provider, dispatcher = Provider(), Dispatcher()
    plane = RuntimeControlPlane(target(provider), distributed_execution=dispatcher, operation_evidence=Evidence())
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        request = dispatcher.commands[0]
        control = BackendOperationControlModel(
            binding=request.binding,
            request_digest=backend_operation_request_digest(request),
            control_id="expired",
            actor_id=worker().identity,
            authorization_scope=("role:backend",),
            action="observe",
            budget={
                "origin_id": "original",
                "started_at": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
                "limit_ms": 1000,
                "remaining_ms": 1000,
            },
        )
        with pytest.raises(TimeoutError):
            plane.record_worker_observation(control, identity=worker())
        assert not plane._store.load_records()[receipt.operation_id].invocation.controls
    finally:
        plane.close()

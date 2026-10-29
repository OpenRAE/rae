"""Real runtime admission and settlement remain honest around blocked backends."""

from dataclasses import replace
from threading import Event, Thread

import pytest
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.errors import AuthorizationError
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from raes_runtime.errors import RuntimeBudgetExhaustedError


def supervisor(target="stub"):
    return ControlPlaneIdentity(
        identity="supervisor-1362", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name=target
    )


def test_blocked_native_apply_allows_stop_and_cancel_then_fences_its_late_success():
    from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration

    entered, release = Event(), Event()
    receipts, failures = [], []

    class Blocked(StubProvisioner):
        def apply(self, plan, snapshot):
            entered.set()
            assert release.wait(3)
            return super().apply(plan, snapshot)

    target = replace(create_stub_target(), provisioner=Blocked())
    plane = RuntimeControlPlane(target, supervision=OperationSupervisionConfiguration(execution_ms=200, drain_ms=50))
    raw_store = plane._store.raw_store

    def submit():
        try:
            receipts.append(plane.submit_provisioning(ProvisioningPlan(), idempotency_key="blocked-1362"))
        except BaseException as exc:  # noqa: BLE001 - the worker hands the exception to the test thread, which asserts it.
            failures.append(exc)

    worker = Thread(target=submit)
    worker.start()
    try:
        assert entered.wait(1)
        record = next(iter(plane._store.load_records().values()))
        parent_id = record.receipt.operation_id
        assert record.invocation.consumed
        control = plane.cancel_operation(parent_id, control_id="cancel-1362", identity=supervisor(target.name))
        assert control.actor_id == "supervisor-1362"
        assert plane.get_operation(parent_id).state is OperationState.RUNNING
        plane.stop_admission(identity=supervisor(target.name))
        assert plane._store.effect_admission_stopped()
        worker.join(1)
        assert not worker.is_alive()
        assert not failures
        assert plane.get_operation(parent_id).state is OperationState.INDETERMINATE
        assert plane._store.load_records()[parent_id].invocation.reserved
        assert plane.submit_provisioning(ProvisioningPlan(), idempotency_key="blocked-1362") == receipts[0]
        with pytest.raises(RuntimeBudgetExhaustedError):
            plane.close()
        assert plane.get_operation(parent_id).state is OperationState.INDETERMINATE
    finally:
        release.set()
        worker.join(1)
        plane.close()
    assert raw_store.load_records()[parent_id].status.state is OperationState.INDETERMINATE


def test_stop_is_scoped_and_an_unauthorized_actor_cannot_close_admission():
    plane = RuntimeControlPlane(create_stub_target())
    try:
        rejected_identity = supervisor("another-target")
        with pytest.raises(AuthorizationError):
            plane.stop_admission(identity=rejected_identity)
        assert not plane._store.effect_admission_stopped()
        receipt = plane.submit_provisioning(ProvisioningPlan())
        assert receipt.accepted
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
    finally:
        plane.close()

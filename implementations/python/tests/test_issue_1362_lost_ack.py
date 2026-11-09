"""Uncertain dispatch and commit acknowledgements keep authority closed."""

from threading import Event

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import OperationalError
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from raes_runtime.errors import RuntimeBudgetExhaustedError
from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration


def test_lost_consumed_write_reply_never_reaches_the_backend():
    class LostGrant(InMemoryControlPlaneStore):
        def save_record(self, record):
            super().save_record(record)
            if record.invocation is not None and record.invocation.consumed:
                raise TimeoutError("fixture lost acknowledgement")

    target = create_stub_target()
    called = Event()
    target.provisioner.apply = lambda *args: called.set()
    store = LostGrant()
    plane = RuntimeControlPlane(target, store=store)
    try:
        rejected_plan = ProvisioningPlan()
        # The poisoned runtime refuses the work with its restart category instead of the store failure.
        with pytest.raises(OperationalError, match="requires restart"):
            plane.submit_provisioning(rejected_plan)
        assert not called.is_set()
        retained = next(iter(store.load_records().values()))
        assert retained.status.state is OperationState.RUNNING
        assert retained.invocation.consumed
        assert plane._durability_poisoned
    finally:
        plane.close()


def test_commit_timeout_does_not_award_readback_a_fresh_budget():
    release = Event()

    class SlowCommit(InMemoryControlPlaneStore):
        def commit_terminal_operation(self, *args, **kwargs):
            result = super().commit_terminal_operation(*args, **kwargs)
            assert release.wait(3)
            return result

    store = SlowCommit()
    plane = RuntimeControlPlane(
        create_stub_target(), store=store, supervision=OperationSupervisionConfiguration(commit_ms=60, drain_ms=60)
    )
    try:
        rejected_plan_1 = ProvisioningPlan()
        with pytest.raises(OperationalError, match="requires restart"):
            plane.submit_provisioning(rejected_plan_1)
        assert plane._durability_poisoned
        with pytest.raises(RuntimeBudgetExhaustedError):
            plane.close()
        assert not plane._closed
    finally:
        release.set()
        assert plane._execution_adapter.drain(timeout_ms=1000)
        plane.close()

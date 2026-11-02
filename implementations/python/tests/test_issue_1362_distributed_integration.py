"""CI-only process loss and reopening with the PostgreSQL ledger."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("phase", ["before-grant", "after-grant", "after-dispatch", "after-terminal"])
def test_actual_process_loss_never_reissues_a_consumed_grant(phase, tmp_path):
    if os.environ.get("RAES_EXECUTION_INTEGRATION") != "1":
        pytest.skip("requires the hosted runtime-execution integration composition")
    from postgresql_ledger_fixtures import disposable_ledger_database

    with disposable_ledger_database() as database:
        _exercise_process_loss(phase, tmp_path, database)


def _exercise_process_loss(phase, tmp_path, database):
    import subprocess
    import sys

    from postgresql_ledger_fixtures import ledger_configuration
    from raes_backend_stubs.stubs import create_stub_target
    from raes_contracts.planning import ProvisioningPlan
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane import RuntimeControlPlane
    from raes_runtime.control_plane_store import IndeterminateClaimBlocked
    from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore

    config = ledger_configuration(database)
    PostgreSQLControlPlaneStore(config).initialize_schema()
    marker = tmp_path / "effect-witness"
    fixture = Path(__file__).with_name("control_plane_supervision_crash_fixture.py")
    stopped = subprocess.run(
        [sys.executable, str(fixture), phase, str(marker), database], timeout=25, capture_output=True
    )
    assert stopped.returncode == 86
    reopened_target = create_stub_target()
    calls = []
    original_apply = reopened_target.provisioner.apply

    def apply(plan, snapshot):
        calls.append(plan)
        return original_apply(plan, snapshot)

    reopened_target.provisioner.apply = apply
    plane = RuntimeControlPlane(reopened_target, store=PostgreSQLControlPlaneStore(config))
    try:
        (record,) = plane._store.load_records().values()
        expected = (
            OperationState.CANCELLED
            if phase == "before-grant"
            else (OperationState.SUCCEEDED if phase == "after-terminal" else OperationState.INDETERMINATE)
        )
        assert record.status.state is expected
        assert record.invocation.consumed == (phase != "before-grant")
        assert marker.exists() == (phase in {"after-dispatch", "after-terminal"})
        receipt = plane.submit_provisioning(ProvisioningPlan(operation_id="crash-case"), idempotency_key="crash-retry")
        assert receipt == record.receipt
        if record.invocation.reserved:
            rejected_plan = ProvisioningPlan()
            with pytest.raises(IndeterminateClaimBlocked, match="indeterminate operation requires resolution"):
                plane.submit_provisioning(rejected_plan)
        assert calls == []
        assert plane._store.load_records()[record.receipt.operation_id].invocation == record.invocation
        assert len([event for event in plane._store.read_audit() if event.action.endswith("_terminal")]) == 1
    finally:
        plane.close()

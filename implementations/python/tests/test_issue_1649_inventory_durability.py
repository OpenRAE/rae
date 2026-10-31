"""The existing control-plane mutation path owns refresh dispatch and durability."""

import pytest
from raes_contracts.errors import OperationalError
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from runtime_descendant_fixtures import descendant_runtime


def test_control_plane_apply_refresh_and_restart_use_committed_inventory(tmp_path):
    manager, backend, plan, target, archive = descendant_runtime(tmp_path)
    manager.close()
    state_dir = tmp_path / "store"
    plane = RuntimeControlPlane(
        target, store=LocalControlPlaneStore(state_dir), materialization_archive=archive, run_scope="run:run-1"
    )
    plane.register_planner_produced_plan(plan)
    receipt = plane.submit_provisioning(plan.provisioning, idempotency_key="initial")
    assert receipt.accepted, receipt.diagnostics
    assert "provision.node.leaf" in plane.snapshot.entries
    backend.members["later"] = "provision.node.leaf"
    refreshed = plane.submit_inventory_refresh(plan.provisioning, idempotency_key="refresh")
    assert refreshed.accepted, refreshed.diagnostics
    assert "provision.node.later" in plane.snapshot.entries
    expected = plane.snapshot
    retried = plane.submit_inventory_refresh(plan.provisioning, idempotency_key="refresh")
    assert retried.operation_id == refreshed.operation_id
    assert backend.applies == 1
    assert backend.refreshes == 1
    plane.close()
    restored = RuntimeControlPlane(
        target, store=LocalControlPlaneStore(state_dir), materialization_archive=archive, run_scope="run:run-1"
    )
    assert restored.snapshot == expected
    assert restored.snapshot.materialization_attestations[-1].inventory.descendants
    restored.close()


def test_rejected_refresh_and_restart_preserve_the_trusted_snapshot(tmp_path):
    manager, backend, plan, target, archive = descendant_runtime(tmp_path)
    manager.close()
    state_dir = tmp_path / "rejected"
    plane = RuntimeControlPlane(
        target, store=LocalControlPlaneStore(state_dir), materialization_archive=archive, run_scope="run:run-1"
    )
    plane.register_planner_produced_plan(plan)
    assert plane.submit_provisioning(plan.provisioning).accepted
    predecessor = plane.snapshot
    backend.mutate = lambda document: document["materialization_provenance"]["inventory"].update(attempt_id="stale")
    receipt = plane.submit_inventory_refresh(plan.provisioning, idempotency_key="invalid")
    assert receipt.accepted
    assert plane.snapshot == predecessor
    assert plane.get_operation(receipt.operation_id).state.value == "indeterminate"
    plane.close()
    restored = RuntimeControlPlane(
        target, store=LocalControlPlaneStore(state_dir), materialization_archive=archive, run_scope="run:run-1"
    )
    assert restored.snapshot == predecessor
    assert restored.submit_inventory_refresh(plan.provisioning, idempotency_key="invalid") == receipt
    assert backend.refreshes == 1
    restored.close()


def test_inventory_refresh_rejects_calls_after_control_plane_close(tmp_path):
    manager, backend, plan, target, archive = descendant_runtime(tmp_path)
    manager.close()
    plane = RuntimeControlPlane(target, materialization_archive=archive, run_scope="run:run-1")
    plane.register_planner_produced_plan(plan)
    assert plane.submit_provisioning(plan.provisioning).accepted
    plane.close()
    with pytest.raises(OperationalError, match="control plane is closed"):
        plane.submit_inventory_refresh(plan.provisioning)
    assert backend.applies == 1
    assert backend.refreshes == 0

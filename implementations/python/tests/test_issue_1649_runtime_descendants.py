"""Descendants enter through public reporting and preserve their causal lineage."""

from raes import parse_sdl
from raes_contracts.planning import PlanScope
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from runtime_descendant_fixtures import ROOT, descendant_runtime


def test_unauthorized_membership_preserves_the_immediate_predecessor(tmp_path):
    manager, backend, plan, _target, _archive = descendant_runtime(
        tmp_path, "name: closed\nrealization: {default: closed}\nnodes:\n  host: {type: compute}"
    )
    predecessor = manager.snapshot
    result = manager.apply(plan)
    assert not result.success
    assert result.snapshot == predecessor
    assert manager.snapshot == predecessor
    assert result.changed_addresses == []
    assert result.materialization_attestation is None
    manager.close()


def test_public_apply_refresh_and_reload_preserve_transitive_descendants(tmp_path):
    manager, backend, plan, target, archive = descendant_runtime(tmp_path)
    original = plan.model.realization_instance.model_dump_json()
    applied = manager.apply(plan)
    assert applied.success, applied.diagnostics
    assert set(applied.snapshot.entries) == {ROOT, "provision.node.worker", "provision.node.leaf"}
    inventory = applied.snapshot.materialization_attestations[-1].inventory
    records = {record.address: record for record in inventory.descendants}
    assert records["provision.node.worker"].parent_address == ROOT
    assert records["provision.node.leaf"].parent_address == "provision.node.worker"
    assert records["provision.node.leaf"].source_address == ROOT

    backend.members["later"] = "provision.node.leaf"
    refreshed = manager.refresh_inventory(plan)
    assert refreshed.success, refreshed.diagnostics
    assert "provision.node.later" in refreshed.snapshot.entries
    later_inventory = refreshed.snapshot.materialization_attestations[-1].inventory
    assert later_inventory.attempt_id != inventory.attempt_id
    assert later_inventory.descendants[0].creation == inventory.descendants[0].creation
    assert backend.applies == 1
    assert backend.refreshes == 1
    assert plan.model.realization_instance.model_dump_json() == original

    store = LocalControlPlaneStore(tmp_path / "state")
    manager.close()
    owner = RuntimeControlPlane(target, store=store, materialization_archive=archive)
    state = store.save_snapshot(refreshed.snapshot, expected_revision=0)
    assert state.revision == 1
    assert owner.snapshot == refreshed.snapshot
    owner.close()
    restored = RuntimeControlPlane(
        target, store=LocalControlPlaneStore(tmp_path / "state"), materialization_archive=archive
    )
    assert restored.snapshot == refreshed.snapshot
    assert restored.snapshot.realization_provenance
    restored.close()


def test_replanning_retains_descendants_and_destroy_uses_accepted_inventory(tmp_path):
    manager, backend, plan, _target, _archive = descendant_runtime(tmp_path)
    assert manager.apply(plan).success
    next_plan = manager.plan(
        parse_sdl("name: dynamic\nrealization: {default: open}\nnodes:\n  host: {type: compute}"),
        run_scope=PlanScope(run_id="run-1"),
    )
    assert not any(operation.action == "delete" for operation in next_plan.provisioning.operations)
    destroyed = manager.destroy()
    assert destroyed.success, destroyed.diagnostics
    assert not destroyed.snapshot.entries
    assert destroyed.snapshot.materialization_attestations
    manager.close()

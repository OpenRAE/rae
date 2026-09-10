"""RUN-314: provisioner apply via the control plane."""

from __future__ import annotations

import textwrap
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.planning import (
    ChangeAction,
    ProvisioningPlan,
    ProvisionOp,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_reference_backend import (
    create_reference_backend_components,
    create_reference_backend_manifest,
)
from raes_reference_backend.drivers.inprocess import InProcessDriver
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.manager import RuntimeManager
from raes_runtime.registry import RuntimeTarget
from realization_authority_fixtures import with_compute_substrate_collection_demand

_SCENARIO = """
name: ref-provisioner
nodes:
  web:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
"""


def _target_with_driver(driver: InProcessDriver) -> RuntimeTarget:
    manifest = create_reference_backend_manifest()
    components = create_reference_backend_components(manifest=manifest, driver=driver)
    return RuntimeTarget(
        name="reference-emulation",
        manifest=manifest,
        provisioner=components.provisioner,
        orchestrator=components.orchestrator,
        evaluator=components.evaluator,
        participant_runtime=components.participant_runtime,
    )


def _provisioning_plan(target: RuntimeTarget) -> ProvisioningPlan:
    manager = RuntimeManager(target)
    execution_plan = manager.plan(parse_sdl(textwrap.dedent(_SCENARIO)))
    return execution_plan.provisioning


def test_apply_via_control_plane_records_entries_and_drives_driver():
    driver = InProcessDriver()
    target = _target_with_driver(driver)
    plan = _provisioning_plan(target)

    control_plane = RuntimeControlPlane(target)
    receipt = control_plane.submit_provisioning(plan)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None
    assert status.state.value == "succeeded"
    snapshot = control_plane.snapshot
    assert "provision.node.web" in snapshot.entries
    assert snapshot.entries["provision.node.web"].status == "applied"
    # The driver was actually invoked to realize the container.
    realized = [op for op in driver.recorded_ops if op.verb == "realize" and op.kind == "container"]
    assert any(op.address == "provision.node.web" for op in realized)


@pytest.mark.parametrize("collect", [False, True])
def test_native_collection_is_selected_before_driver_readback_and_never_persisted(collect):
    class Driver(InProcessDriver):
        def realize(self, **kwargs):
            result = super().realize(**kwargs)
            assert result.observations == ()
            return result

        def observe(self, *, containers):
            calls.append(tuple(spec.address for spec in containers))
            return super().observe(containers=containers)

    calls = []
    target = _target_with_driver(Driver())
    planned = replace(_provisioning_plan(target), operation_id="native-boundary")
    if collect:
        planned = with_compute_substrate_collection_demand(
            planned,
            semantic_scope="/nodes/web",
            address="provision.node.web",
        )
    result = target.provisioner.apply(planned, RuntimeSnapshot())
    assert result.success
    assert calls == ([("provision.node.web",)] if collect else [])
    assert result.snapshot.realization_observations == ()
    assert bool(result.operational_realization_observations) == collect


def test_apply_handles_delete_and_unchanged():
    driver = InProcessDriver()
    target = _target_with_driver(driver)
    plan = _provisioning_plan(target)
    control_plane = RuntimeControlPlane(target)
    control_plane.submit_provisioning(plan)
    assert control_plane.snapshot.realization_observations == ()

    # Now submit a DELETE for the realized node.
    delete_plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.DELETE,
                address="provision.node.web",
                resource_type="node",
                payload={},
            )
        ]
    )
    receipt = control_plane.submit_provisioning(delete_plan)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None and status.state.value == "succeeded"
    assert "provision.node.web" not in control_plane.snapshot.entries
    assert control_plane.snapshot.realization_observations == ()
    destroyed = [op for op in driver.recorded_ops if op.verb == "destroy" and op.kind == "container"]
    assert any(op.address == "provision.node.web" for op in destroyed)


def test_unchanged_op_keeps_entry_without_driver_realize():
    driver = InProcessDriver()
    target = _target_with_driver(driver)
    planned = _provisioning_plan(target)
    control_plane = RuntimeControlPlane(target)
    control_plane.submit_provisioning(planned)
    realizes_before = tuple(op for op in driver.recorded_ops if op.verb == "realize")
    unchanged_plan = replace(
        planned,
        operations=[
            replace(operation, action=ChangeAction.UNCHANGED)
            for operation in planned.operations
            if operation.address == "provision.node.web"
        ],
    )
    control_plane.submit_provisioning(unchanged_plan)

    entry = control_plane.snapshot.entries["provision.node.web"]
    assert entry.status == "unchanged"
    assert tuple(op for op in driver.recorded_ops if op.verb == "realize") == realizes_before


def test_unchanged_compute_uses_non_retained_operational_readback() -> None:
    observe_calls: list[tuple[str, ...]] = []

    class _ObservationRecordingDriver(InProcessDriver):
        def observe(self, *, containers):
            observe_calls.append(tuple(container.address for container in containers))
            return super().observe(containers=containers)

    driver = _ObservationRecordingDriver()
    target = _target_with_driver(driver)
    scenario = parse_sdl(textwrap.dedent(_SCENARIO))
    create_plan = RuntimeManager(target).plan(scenario).provisioning
    first = RuntimeControlPlane(target)
    first.submit_provisioning(create_plan)
    legacy_snapshot = replace(first.snapshot, realization_observations=())
    realizes_before = tuple(op for op in driver.recorded_ops if op.verb == "realize")
    observes_before = len(observe_calls)
    unchanged_plan = RuntimeManager(target).plan(scenario, legacy_snapshot).provisioning
    assert all(operation.action is ChangeAction.UNCHANGED for operation in unchanged_plan.operations)
    unchanged_plan = with_compute_substrate_collection_demand(
        unchanged_plan,
        semantic_scope="/nodes/web",
        address="provision.node.web",
    )

    upgraded = RuntimeControlPlane(target, initial_snapshot=legacy_snapshot)
    receipt = upgraded.submit_provisioning(unchanged_plan)

    assert upgraded.get_operation(receipt.operation_id).state.value == "succeeded"
    assert upgraded.snapshot.realization_observations == ()
    assert tuple(op for op in driver.recorded_ops if op.verb == "realize") == realizes_before
    assert len(observe_calls) == observes_before + 1
    assert observe_calls[-1] == ("provision.node.web",)


def test_snapshot_payload_carries_only_portable_facts():
    driver = InProcessDriver()
    target = _target_with_driver(driver)
    plan = _provisioning_plan(target)
    control_plane = RuntimeControlPlane(target)
    control_plane.submit_provisioning(plan)

    snapshot = control_plane.snapshot
    entry = snapshot.entries["provision.node.web"]
    operation = next(operation for operation in plan.operations if operation.address == entry.address)

    assert entry.payload == operation.payload

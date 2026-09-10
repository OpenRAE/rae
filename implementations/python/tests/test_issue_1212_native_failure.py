"""Native observation failures preserve resource accounting, not success claims."""

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from raes_runtime.manager import RuntimeManager
from realization_authority_fixtures import with_compute_substrate_collection_demand
from test_cross_backend_minimal_scenario import _targets

_SCENARIO = """
name: native-readback-boundary
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
"""


@pytest.mark.parametrize("backend", ["reference", "libvirt"])
@pytest.mark.parametrize("failure", ["diagnostic", "exception", "missing", "malformed", "invalid", "duplicate"])
def test_failed_post_creation_readback_remains_in_recoverable_inventory(backend, failure, monkeypatch):
    target = dict(_targets())[backend]
    driver = target.provisioner._driver
    ordinary_observe = driver.observe
    ordinary_realize = driver.realize
    calls = []

    def realize(**kwargs):
        return replace(ordinary_realize(**kwargs), observations=())

    def fail_observe(**kwargs):
        calls.append("observe")
        if failure == "exception":
            raise RuntimeError("private native output")
        if failure == "malformed":
            return object()
        result = ordinary_observe(**kwargs)
        if failure == "invalid":
            return replace(result, observations=(replace(result.observations[0], sequence="invalid"),))
        if failure == "duplicate":
            return replace(result, observations=(*result.observations, *result.observations))
        return replace(
            result,
            observations=(),
            diagnostics=(
                Diagnostic(
                    code="test.native-readback-failed",
                    domain="runtime",
                    address="provision.node.vm",
                    message="Readback failed.",
                ),
            )
            if failure == "diagnostic"
            else (),
        )

    monkeypatch.setattr(driver, "observe", fail_observe)
    monkeypatch.setattr(driver, "realize", realize)
    plan = with_compute_substrate_collection_demand(
        RuntimeManager(target).plan(parse_sdl(_SCENARIO)).provisioning,
        semantic_scope="/nodes/vm",
        address="provision.node.vm",
    )
    store = InMemoryControlPlaneStore()
    cp = RuntimeControlPlane(target, store=store)
    receipt = cp.submit_provisioning(plan)
    assert receipt.accepted
    status = cp.get_operation(receipt.operation_id)
    assert status.state.value == "failed"
    assert calls == ["observe"]
    assert "private native output" not in repr(status)
    assert "provision.node.vm" in cp.snapshot.entries
    assert "provision.node.vm" in driver.realized_addresses()
    assert "provision.node.vm" in status.changed_addresses
    assert cp.snapshot.realization_observations == ()
    assert cp.snapshot.realization_provenance == ()
    recovered = RuntimeControlPlane(target, store=store)
    assert recovered.snapshot.entries == cp.snapshot.entries
    cleanup = recovered.submit_provisioning(
        ProvisioningPlan(
            realization_envelope=target.manifest.realization_envelope.identity,
            operations=[
                ProvisionOp(action=ChangeAction.DELETE, address="provision.node.vm", resource_type="node", payload={}),
            ],
        )
    )
    assert recovered.get_operation(cleanup.operation_id).state.value == "succeeded"
    assert recovered.snapshot.entries == {}
    assert not driver.realized_addresses()


@pytest.mark.parametrize("backend", ["reference", "libvirt"])
def test_manager_preserves_inventory_when_native_readback_raises(backend, monkeypatch):
    target = dict(_targets())[backend]
    manager = RuntimeManager(target)
    execution = manager.plan(parse_sdl(_SCENARIO))
    demanded = with_compute_substrate_collection_demand(
        execution.provisioning,
        semantic_scope="/nodes/vm",
        address="provision.node.vm",
    )

    def fail_observe(**_):
        raise RuntimeError("private native output")

    monkeypatch.setattr(target.provisioner._driver, "observe", fail_observe)
    result = manager.apply(replace(execution, provisioning=demanded))
    assert not result.success
    assert "provision.node.vm" in result.snapshot.entries
    assert "provision.node.vm" in result.changed_addresses
    assert "private native output" not in repr(result.diagnostics)
    assert result.snapshot.realization_observations == ()
    assert result.snapshot.realization_provenance == ()


@pytest.mark.parametrize("backend", ["reference", "libvirt"])
def test_retained_backend_selected_description_never_calls_native_observe(backend, monkeypatch):
    target = dict(_targets())[backend]
    monkeypatch.setattr(target.provisioner._driver, "observe", lambda **_: pytest.fail("unexpected native probe"))
    scenario = parse_sdl(
        _SCENARIO
        + """
evidence_requirements:
  apparatus:
    source_class: processor_backend
    scope_refs: [nodes.vm]
    window: run
    channel: api_response
    sensitivity: plain
    redaction: none
    integrity: none
    retention: not_retained
    loss_disclosure: required
    observation_demand:
      rule_id: apparatus
      scope: /nodes/vm
      purpose: realization-description
      mode: selected
      selector: {semantic_scope: /nodes/vm, data_kind: field, names: [compute-substrate]}
      collection: require
      retention: require
      basis: backend-selected
"""
    )
    store = InMemoryControlPlaneStore()
    cp = RuntimeControlPlane(target, store=store)
    receipt = cp.submit_provisioning(RuntimeManager(target).plan(scenario).provisioning)
    assert receipt.accepted
    assert cp.get_operation(receipt.operation_id).state.value == "succeeded"
    assert cp.snapshot.realization_observations == ()
    description = RuntimeControlPlane(target, store=store).observation_execution(receipt.operation_id)
    assert len(description.realized_form_disclosures) == 1
    assert description.realized_form_disclosures[0].basis == "backend-realized"
    assert description.realized_form_disclosures[0].evidence_refs == []


@pytest.mark.parametrize("backend", ["reference", "libvirt"])
def test_failed_readback_inventory_still_enforces_materialization_authority(backend, monkeypatch):
    from copy import deepcopy

    target = dict(_targets())[backend]
    original_apply = target.provisioner.apply

    def altered_failed_apply(plan, snapshot):
        result = original_apply(plan, snapshot)
        entries = dict(result.snapshot.entries)
        entry = entries["provision.node.vm"]
        payload = deepcopy(entry.payload)
        payload["node_kind"] = "switch"
        entries[entry.address] = replace(entry, payload=payload)
        return replace(result, success=False, snapshot=result.snapshot.with_entries(entries))

    monkeypatch.setattr(target.provisioner, "apply", altered_failed_apply)
    cp = RuntimeControlPlane(target)
    receipt = cp.submit_provisioning(RuntimeManager(target).plan(parse_sdl(_SCENARIO)).provisioning)
    assert receipt.accepted
    status = cp.get_operation(receipt.operation_id)
    assert status.state.value == "failed"
    assert any(diagnostic.code == "runtime.backend-contract-invalid" for diagnostic in status.diagnostics)
    assert cp.snapshot.entries == {}

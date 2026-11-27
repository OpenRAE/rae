"""Relayed provisioning plans realize their published operations (issue #1425).

The authenticated HTTP route carries the published plan model, which holds
operations and no processor-internal ``resources`` map. Backends derive their
realized specs from ``planned_provisioning_resources``: the digest-bound
non-delete operations. A relayed plan therefore yields the same resources as
the same plan in process, a deleted address is never realized, and a
``resources`` map outside the plan digest cannot change what a backend builds.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes.instantiate import instantiate_scenario
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.contracts.plan_projection import (
    planned_provisioning_resources,
    provisioning_plan_model,
    runtime_plan_digest,
)
from raes_contracts.planning import ChangeAction, ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan as plan_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api_models import _provisioning_plan
from runtime_plan_fixtures import plan_for_target
from starlette.testclient import TestClient
from test_runtime_control_plane_api import _test_security

_SCENARIO = """
name: relay-parity
nodes:
  lab: {type: switch}
  web: {type: compute, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  lab: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  web: {count: 1, links: [lab]}
"""

# Applied first: the issue scenario plus node db and accounts alice and bob on web.
_EXTENDED = """
name: relay-parity
nodes:
  lab: {type: switch}
  web: {type: compute, resources: {ram: 1 gib, cpu: 1}}
  db: {type: compute, resources: {ram: 1 gib, cpu: 1}}
infrastructure:
  lab: {count: 1, properties: {cidr: 10.0.0.0/24, gateway: 10.0.0.1}}
  web: {count: 1, links: [lab]}
  db: {count: 1, links: [lab]}
accounts:
  alice: {username: alice, node: web}
  bob: {username: bob, node: web}
"""

# Re-planned against the snapshot _EXTENDED leaves, this deletes node db and account alice.
_REDUCED = _SCENARIO + "accounts:\n  bob: {username: bob, node: web}\n  carol: {username: carol, node: web}\n"


def _provisioning(scenario: str, snapshot: RuntimeSnapshot | None = None) -> ProvisioningPlan:
    model = compile_runtime_model(instantiate_scenario(parse_sdl(scenario)))
    return plan_runtime_model(model, create_stub_target().manifest, snapshot).provisioning


def _nodes(plan: ProvisioningPlan) -> list:
    """The node resources a backend realizes from the plan's backend-facing view."""

    return [resource for resource in planned_provisioning_resources(plan) if resource.resource_type == "node"]


def _relayed(plan: ProvisioningPlan) -> ProvisioningPlan:
    """The plan as the authenticated HTTP route rebuilds it from its published model."""

    return _provisioning_plan(provisioning_plan_model(plan))


def _applied(plan: ProvisioningPlan) -> RuntimeSnapshot:
    """The snapshot left by applying every operation of a plan made without one."""

    return RuntimeSnapshot(
        entries={
            op.address: SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=op.resource_type,
                payload=op.payload,
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
            )
            for op in plan.operations
        }
    )


def _with_node_source(plan: ProvisioningPlan, source: str) -> ProvisioningPlan:
    """The plan with only the web node image in its ``resources`` map rewritten."""

    node = plan.resources["provision.node.web"]
    payload = deepcopy(node.payload)
    payload["spec"]["node"]["source"] = source
    return replace(plan, resources={**plan.resources, node.address: replace(node, payload=payload)})


class _RecordingProvisioner(StubProvisioner):
    """The stub provisioner, also recording each resource a backend would realize."""

    def __init__(self, realization_envelope) -> None:
        super().__init__(realization_envelope)
        self.realized: list = []

    def apply(self, plan, snapshot):
        self.realized.extend(planned_provisioning_resources(plan))
        return super().apply(plan, snapshot)

    def realized_addresses(self) -> set[str]:
        return {resource.address for resource in self.realized}


@pytest.fixture
def recording():
    """A control plane over the stub target, its recording provisioner, and a registered plan."""

    stub = create_stub_target()
    provisioner = _RecordingProvisioner(stub.manifest.realization_envelope)
    target = replace(stub, provisioner=provisioner)
    control = RuntimeControlPlane(target)
    execution = plan_for_target(target, parse_sdl(_SCENARIO))
    control.register_planner_produced_plan(execution)
    yield control, provisioner, execution.provisioning
    control.close()


def test_http_relayed_plan_realizes_every_committed_address(recording):
    control, provisioner, provisioning = recording
    wire = provisioning_plan_model(provisioning).model_dump(mode="json", exclude_none=True)
    app = create_control_plane_app(control, security=_test_security("stub"))

    with TestClient(app) as client:
        response = client.post(
            "/operations/provisioning", json=wire, headers={"authorization": "Bearer test-operator-token"}
        )
        assert response.is_success, response.text
        assert control.get_operation(response.json()["operation_id"]).state is OperationState.SUCCEEDED
        committed = set(control.snapshot.entries)

    assert committed == {"provision.network.lab", "provision.node.web"}
    assert provisioner.realized_addresses() == committed


def test_relayed_and_direct_plans_expose_identical_backend_resources():
    direct = _provisioning(_SCENARIO)
    relayed = _relayed(direct)

    assert relayed.resources == {}
    assert planned_provisioning_resources(relayed) == planned_provisioning_resources(direct)
    assert _nodes(relayed)


def test_deleted_addresses_are_never_realized():
    """A re-plan that deletes a node and an account realizes what a fresh plan of the rest realizes."""

    replanned = _provisioning(_REDUCED, _applied(_provisioning(_EXTENDED)))
    remaining = planned_provisioning_resources(_provisioning(_REDUCED))

    assert {op.address for op in replanned.operations if op.action is ChangeAction.DELETE} == {
        "provision.node.db",
        "provision.account.alice",
    }
    assert [resource.address for resource in remaining if resource.resource_type == "node"] == ["provision.node.web"]
    for candidate in (replanned, _relayed(replanned)):
        addresses = {resource.address for resource in planned_provisioning_resources(candidate)}
        assert "provision.node.db" not in addresses
        assert "provision.account.alice" not in addresses
        assert _nodes(candidate) == _nodes(_provisioning(_REDUCED))


def test_resources_map_outside_the_plan_digest_cannot_change_the_backend_resources():
    honest = _provisioning(_SCENARIO)
    tampered = _with_node_source(honest, "attacker/backdoor:latest")

    assert runtime_plan_digest(tampered) == runtime_plan_digest(honest)
    assert planned_provisioning_resources(tampered) == planned_provisioning_resources(honest)


def test_resources_map_outside_the_plan_digest_cannot_change_the_realized_image(recording):
    control, provisioner, honest = recording
    tampered = _with_node_source(honest, "attacker/backdoor:latest")
    assert runtime_plan_digest(tampered) == runtime_plan_digest(honest)

    receipt = control.submit_provisioning(tampered)
    assert control.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
    realized_sources = [
        resource.payload["spec"]["node"].get("source")
        for resource in provisioner.realized
        if resource.resource_type == "node"
    ]
    assert realized_sources == [resource.payload["spec"]["node"].get("source") for resource in _nodes(honest)]
    assert "attacker/backdoor:latest" not in realized_sources

"""Relayed provisioning plans realize their published operations (issue #1425).

The authenticated HTTP route carries the published plan model, which holds
operations and no processor-internal ``resources`` map. The reference and
libvirt interpreters derive their realized specs from the digest-bound
non-delete operations, so a relayed plan yields the same specs as the same plan
in process, a deleted address is never realized, and a ``resources`` map
outside the plan digest cannot change the specs those interpreters build.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace

import pytest
from raes import parse_sdl
from raes.instantiate import instantiate_scenario
from raes_backend_libvirt.manifest import create_libvirt_manifest
from raes_backend_libvirt.realization import interpret_provisioning_plan as interpret_libvirt
from raes_contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
from raes_contracts.planning import ChangeAction, ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan as plan_runtime_model
from raes_reference_backend import REFERENCE_BACKEND_NAME, create_reference_backend_target
from raes_reference_backend.drivers.inprocess import InProcessDriver
from raes_reference_backend.realization import interpret_provisioning_plan as interpret_reference
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api_models import _provisioning_plan
from raes_runtime.manager import RuntimeManager
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

_INTERPRETERS = pytest.mark.parametrize(
    ("manifest", "interpret", "realized"),
    [
        (lambda: create_reference_backend_target().manifest, interpret_reference, "containers"),
        (create_libvirt_manifest, interpret_libvirt, "domains"),
    ],
    ids=["reference", "libvirt"],
)


def _provisioning(scenario: str, manifest, snapshot: RuntimeSnapshot | None = None) -> ProvisioningPlan:
    model = compile_runtime_model(instantiate_scenario(parse_sdl(scenario)))
    return plan_runtime_model(model, manifest, snapshot).provisioning


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


@dataclass
class _RecordingDriver(InProcessDriver):
    """The in-process driver, also recording each container spec it realizes."""

    containers: list = field(default_factory=list)

    def realize(self, *, networks, containers):
        self.containers.extend(containers)
        return super().realize(networks=networks, containers=containers)


@pytest.fixture
def recording():
    """A control plane over the reference target, its recording driver, and a registered plan."""

    driver = _RecordingDriver()
    target = create_reference_backend_target(driver=driver)
    control = RuntimeControlPlane(target)
    execution = RuntimeManager(target).plan(parse_sdl(_SCENARIO))
    control.register_planner_produced_plan(execution)
    yield control, driver, execution.provisioning
    control.close()


def test_http_relayed_plan_realizes_every_committed_address(recording):
    control, driver, provisioning = recording
    wire = provisioning_plan_model(provisioning).model_dump(mode="json", exclude_none=True)
    app = create_control_plane_app(control, security=_test_security(REFERENCE_BACKEND_NAME))

    with TestClient(app) as client:
        response = client.post(
            "/operations/provisioning", json=wire, headers={"authorization": "Bearer test-operator-token"}
        )
        assert response.is_success, response.text
        assert control.get_operation(response.json()["operation_id"]).state is OperationState.SUCCEEDED
        committed = set(control.snapshot.entries)

    assert committed == {"provision.network.lab", "provision.node.web"}
    assert driver.realized_addresses() == committed


@_INTERPRETERS
def test_relayed_and_direct_plans_interpret_identically(manifest, interpret, realized):
    direct = _provisioning(_SCENARIO, manifest())
    relayed = _relayed(direct)

    assert relayed.resources == {}
    assert interpret(relayed) == interpret(direct)
    assert getattr(interpret(relayed), realized)


@_INTERPRETERS
def test_deleted_addresses_are_never_realized(manifest, interpret, realized):
    """A re-plan that deletes a node and an account realizes what a fresh plan of the rest realizes.

    For libvirt this also keeps the removed account out of its node's cloud-init.
    """

    replanned = _provisioning(_REDUCED, manifest(), _applied(_provisioning(_EXTENDED, manifest())))
    remaining = interpret(_provisioning(_REDUCED, manifest()))

    assert {op.address for op in replanned.operations if op.action is ChangeAction.DELETE} == {
        "provision.node.db",
        "provision.account.alice",
    }
    assert [spec.address for spec in getattr(remaining, realized)] == ["provision.node.web"]
    assert interpret(replanned) == remaining
    assert interpret(_relayed(replanned)) == remaining


@_INTERPRETERS
def test_resources_map_outside_the_plan_digest_cannot_change_the_interpreted_specs(manifest, interpret, realized):
    honest = _provisioning(_SCENARIO, manifest())
    tampered = _with_node_source(honest, "attacker/backdoor:latest")

    assert runtime_plan_digest(tampered) == runtime_plan_digest(honest)
    assert getattr(interpret(tampered), realized) == getattr(interpret(honest), realized)


def test_resources_map_outside_the_plan_digest_cannot_change_the_realized_image(recording):
    control, driver, honest = recording
    tampered = _with_node_source(honest, "attacker/backdoor:latest")
    assert runtime_plan_digest(tampered) == runtime_plan_digest(honest)

    receipt = control.submit_provisioning(tampered)
    assert control.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
    assert [spec.image_ref for spec in driver.containers] == [
        spec.image_ref for spec in interpret_reference(honest).containers
    ]
    assert "attacker/backdoor:latest" not in {spec.image_ref for spec in driver.containers}

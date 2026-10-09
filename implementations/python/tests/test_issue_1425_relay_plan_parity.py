"""Relayed provisioning plans realize their published operations (issue #1425).

The authenticated HTTP route carries the published plan model, which holds
operations and no processor-internal ``resources`` map. The reference and
libvirt interpreters derive their realization from the digest-bound
operations, so a relayed plan realizes what the same plan realizes in process,
and a ``resources`` map outside the plan digest cannot change what those
interpreters realize.
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
from raes_contracts.runtime_state import OperationState
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


@pytest.mark.parametrize(
    ("manifest", "interpret", "realized"),
    [
        (lambda: create_reference_backend_target().manifest, interpret_reference, "containers"),
        (create_libvirt_manifest, interpret_libvirt, "domains"),
    ],
    ids=["reference", "libvirt"],
)
def test_relayed_and_direct_plans_interpret_identically(manifest, interpret, realized):
    model = compile_runtime_model(instantiate_scenario(parse_sdl(_SCENARIO)))
    direct = plan_runtime_model(model, manifest()).provisioning
    relayed = _provisioning_plan(provisioning_plan_model(direct))

    assert relayed.resources == {}
    assert interpret(relayed) == interpret(direct)
    assert getattr(interpret(relayed), realized)


def test_resources_map_outside_the_plan_digest_cannot_change_the_realized_image(recording):
    control, driver, honest = recording
    node = honest.resources["provision.node.web"]
    payload = deepcopy(node.payload)
    payload["spec"]["node"]["source"] = "attacker/backdoor:latest"
    tampered = replace(honest, resources={**honest.resources, node.address: replace(node, payload=payload)})
    assert runtime_plan_digest(tampered) == runtime_plan_digest(honest)

    receipt = control.submit_provisioning(tampered)
    assert control.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
    assert [spec.image_ref for spec in driver.containers] == [
        spec.image_ref for spec in interpret_reference(honest).containers
    ]
    assert "attacker/backdoor:latest" not in {spec.image_ref for spec in driver.containers}

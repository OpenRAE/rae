"""Inventory refresh retains the existing authenticated provisioning boundary."""

from dataclasses import replace

from raes_contracts.contracts.plan_projection import provisioning_plan_model
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from runtime_descendant_fixtures import descendant_runtime
from starlette.testclient import TestClient
from test_runtime_control_plane_api import _test_security


def test_authenticated_refresh_dispatches_without_apply_and_rejects_untrusted_plan(tmp_path):
    manager, backend, plan, target, archive = descendant_runtime(tmp_path)
    manager.close()
    plane = RuntimeControlPlane(target, materialization_archive=archive, run_scope="run:run-1")
    plane.register_planner_produced_plan(plan)
    assert plane.submit_provisioning(plan.provisioning).accepted
    backend.members["later"] = "provision.node.leaf"
    app = create_control_plane_app(plane, security=_test_security(target.name))
    wire = provisioning_plan_model(replace(plan.provisioning, inventory_refresh=True)).model_dump(
        mode="json", exclude_none=True
    )
    with TestClient(app) as client:
        denied = client.post("/operations/provisioning", json=wire)
        assert denied.status_code == 401
        assert backend.refreshes == 0
        headers = {"authorization": "Bearer test-operator-token", "idempotency-key": "refresh-http"}
        admitted = client.post("/operations/provisioning", json=wire, headers=headers)
        assert admitted.status_code == 200, admitted.text
        assert "provision.node.later" in plane.snapshot.entries
        assert backend.applies == 1
        assert backend.refreshes == 1
        wire["materialization_source"]["target_scope"] = "target:foreign"
        rejected = client.post("/operations/provisioning", json=wire, headers={**headers, "idempotency-key": "foreign"})
        assert rejected.status_code == 403
        assert backend.refreshes == 1

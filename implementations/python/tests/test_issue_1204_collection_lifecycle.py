"""Prepared node authority survives authenticated submission and durable lifecycle."""

from copy import deepcopy

import pytest
from raes import parse_sdl
from raes_contracts.plan_projection import provisioning_plan_model
from raes_contracts.planning import ChangeAction, ProvisionOp
from raes_contracts.runtime_state import OperationState
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_store import _snapshot_payload
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.manager import RuntimeManager
from raes_runtime.registry import RuntimeTarget
from starlette.testclient import TestClient
from test_issue_1204_resource_collections import _collection_request, _isolated_designation, _PreparingNodes
from test_runtime_control_plane_api import _test_security


def _scenario():
    source = "name: collection-lifecycle\n" + _isolated_designation(True) + "\nnodes:\n"
    return parse_sdl(source + "\n".join(f"  n{index}: {{type: compute}}" for index in range(5)))


@pytest.mark.parametrize("tamper", ["binding", "null"])
def test_authenticated_api_rejects_collection_tampering_before_any_backend_callback(tamper):
    _, manifest = _collection_request(_isolated_designation(True))
    calls = []

    class RecordingBackend(_PreparingNodes):
        def prepare(self, request, snapshot):
            calls.append("prepare")
            return super().prepare(request, snapshot)

    backend = RecordingBackend(manifest)
    target = RuntimeTarget(name="prepared-collection", manifest=manifest, provisioner=backend)
    control_plane = RuntimeControlPlane(target)
    execution = plan(compile_runtime_model(_scenario()), manifest, target_name=target.name)
    control_plane.register_planner_produced_plan(execution)
    payload = provisioning_plan_model(execution.provisioning).model_dump(mode="json", exclude_none=True)
    tampered = deepcopy(payload)
    if tamper == "null":
        tampered["preparation"]["node_collection"] = None
    else:
        tampered["preparation"]["node_collection"]["constraint_binding"] = "sha256:" + "0" * 64
    app = create_control_plane_app(control_plane, security=_test_security(target.name))
    headers = {"authorization": "Bearer test-operator-token"}
    with TestClient(app) as client:
        rejected = client.post("/operations/provisioning", json=tampered, headers=headers)
        assert rejected.status_code == 403
        assert rejected.json() == {"detail": "provisioning plan is not planner-authorized"}
        assert calls == []
        assert backend.applies == 0
        accepted = client.post("/operations/provisioning", json=payload, headers=headers)
        assert accepted.is_success, accepted.text
        receipt = accepted.json()
        assert receipt["accepted"], receipt
        assert control_plane.get_operation(receipt["operation_id"]).state is OperationState.SUCCEEDED
        assert len(control_plane.snapshot.entries) == 6
    assert calls == ["prepare"]
    assert backend.applies == 1
    control_plane.close()


def test_rejected_prepared_node_update_keeps_admitted_extra_across_durable_reload(tmp_path):
    _, manifest = _collection_request(_isolated_designation(True))

    class ChangingBackend(_PreparingNodes):
        reject_delivery = False

        def prepare(self, request, snapshot):
            if "provision.node.extra" not in snapshot.entries:
                return super().prepare(request, snapshot)
            from raes_contracts.realization_preparation import RealizationPreparation

            entry = snapshot.entries["provision.node.extra"]
            update = ProvisionOp(ChangeAction.UPDATE, entry.address, entry.resource_type, deepcopy(entry.payload))
            return RealizationPreparation.for_request(request, snapshot, operations=(*request.operations, update))

        def apply(self, request, snapshot):
            result = super().apply(request, snapshot)
            if self.reject_delivery:
                result.snapshot.entries["provision.node.extra"].payload["count"] = 99
            return result

    backend = ChangingBackend(manifest)
    target = RuntimeTarget(name="durable-collection", manifest=manifest, provisioner=backend)
    store = LocalControlPlaneStore(tmp_path / "prepared-state")
    owner = RuntimeControlPlane(target, store=store)
    first = plan(compile_runtime_model(_scenario()), manifest, owner.snapshot, target_name=target.name)
    owner.register_planner_produced_plan(first)
    receipt = owner.submit_provisioning(first.provisioning)
    assert owner.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
    predecessor = _snapshot_payload(owner.snapshot)
    assert "provision.node.extra" in owner.snapshot.entries
    second = plan(compile_runtime_model(_scenario()), manifest, owner.snapshot, target_name=target.name)
    owner.register_planner_produced_plan(second)
    backend.reject_delivery = True
    receipt = owner.submit_provisioning(second.provisioning)
    status = owner.get_operation(receipt.operation_id)
    assert status.state is OperationState.FAILED
    assert status.diagnostics[0].message == "Backend did not deliver its admitted portable node completion."
    assert status.changed_addresses == []
    assert _snapshot_payload(owner.snapshot) == predecessor
    owner.close()
    recovered = RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "prepared-state"))
    assert _snapshot_payload(recovered.snapshot) == predecessor
    assert recovered.get_operation(receipt.operation_id).state is OperationState.FAILED
    recovered.close()


def test_manager_destroy_removes_admitted_additional_nodes():
    _, manifest = _collection_request(_isolated_designation(True))
    backend = _PreparingNodes(manifest)
    target = RuntimeTarget(name="destroy-collection", manifest=manifest, provisioner=backend)
    owner = RuntimeManager(target)
    applied = owner.apply(owner.plan(_scenario()))
    assert applied.success, applied.diagnostics
    assert len(owner.snapshot.entries) == 6
    destroyed = owner.destroy()
    assert destroyed.success, destroyed.diagnostics
    assert owner.snapshot.entries == {}
    assert "provision.node.extra" in destroyed.changed_addresses

"""Target profile execution, authentication and durable carriage through a stub double."""

from dataclasses import replace
from types import MethodType

import pytest
from raes import parse_sdl
from t1_profile_targets import profile_stub_target
from test_issue_1202_domain_profiles import _context, _support
from test_issue_1204_profile_carrier import _profiles


def _profile_case(namespace="com.example.private"):
    from raes_contracts.domain_profiles import DomainProfileOperation

    authority, _ = _profiles(namespace)
    definition = authority.definitions[0].definition
    context = _context(definition, support_declarations=(_support(definition, *DomainProfileOperation),))
    choices = {definition.coordinate.definition_digest: {"name": "green"}}
    return authority, context, choices


@pytest.mark.parametrize("namespace", ["org.openrae.standard", "com.example.private"])
def test_target_executes_profiles_and_reconciles_without_reselecting(namespace):
    from raes_contracts.planning import ChangeAction
    from raes_runtime.manager import RuntimeManager

    authority, context, choices = _profile_case(namespace)
    target = profile_stub_target(context, choices)
    manager = RuntimeManager(target)
    scenario = parse_sdl("name: profiles\nnodes:\n  host: {type: compute}\n")
    execution = manager.plan(scenario, profile_authority=authority)
    assert not [item for item in execution.diagnostics if item.is_error]
    result = manager.apply(execution)
    assert result.success, result.diagnostics
    assert "provision.node.host" in result.snapshot.entries
    assert result.snapshot.entries["provision.node.host"].profile_bindings[0].value == {"name": "green"}
    replanned = manager.plan(scenario, profile_authority=authority)
    assert replanned.provisioning.operations[0].action is ChangeAction.UNCHANGED
    second = manager.apply(replanned)
    assert second.success, second.diagnostics
    assert second.changed_addresses == []
    assert manager.destroy().success
    assert manager.snapshot.entries == {}


def test_target_registration_checks_pinned_profile_context():
    _, context, choices = _profile_case()
    target = profile_stub_target(context, choices)
    target.provisioner.domain_profile_context = context.model_copy(update={"support_declarations": ()})
    with pytest.raises(ValueError, match="profile"):
        replace(target, name="changed-context")


def test_profile_authentication_and_rejected_delivery_preserve_durable_predecessor(tmp_path):
    from copy import deepcopy

    from raes_contracts.contracts.plan_projection import provisioning_plan_model
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane import RuntimeControlPlane
    from raes_runtime.control_plane_api import create_control_plane_app
    from raes_runtime.control_plane_store import _snapshot_payload
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore
    from starlette.testclient import TestClient
    from test_runtime_control_plane_api import _test_security

    authority, context, choices = _profile_case()
    target = profile_stub_target(context, choices)
    applied = []
    ordinary_apply = target.provisioner.apply

    def counting_apply(self, request, snapshot):
        applied.append(request.operation_id)
        return ordinary_apply(request, snapshot)

    # A bound method preserves the target-owned preparation context.
    target.provisioner.apply = MethodType(counting_apply, target.provisioner)
    store = LocalControlPlaneStore(tmp_path / "profile-state")
    control = RuntimeControlPlane(target, store=store)
    scenario = parse_sdl("name: profiles\nnodes:\n  host: {type: compute, resources: {cpu: 1, ram: 1 gib}}\n")
    from runtime_plan_fixtures import plan_for_target

    execution = plan_for_target(target, scenario, profile_authority=authority)
    control.register_planner_produced_plan(execution)
    wire = provisioning_plan_model(execution.provisioning).model_dump(mode="json", exclude_none=True)
    altered = deepcopy(wire)
    altered["profile_authority"]["bindings"][0]["value"]["name"] = "green"
    app = create_control_plane_app(control, security=_test_security(target.name))
    with TestClient(app) as client:
        response = client.post(
            "/operations/provisioning", json=altered, headers={"authorization": "Bearer test-operator-token"}
        )
        assert response.status_code == 403
        assert applied == []
        assert control.snapshot.entries == {}
        accepted = client.post(
            "/operations/provisioning", json=wire, headers={"authorization": "Bearer test-operator-token"}
        )
        assert accepted.is_success, accepted.text
        receipt = accepted.json()
        assert control.get_operation(receipt["operation_id"]).state is OperationState.SUCCEEDED
        before = _snapshot_payload(control.snapshot)
        second = plan_for_target(
            target,
            parse_sdl("name: profiles\nnodes:\n  host: {type: compute, resources: {cpu: 2, ram: 1 gib}}\n"),
            snapshot=control.snapshot,
            profile_authority=authority,
        )
        control.register_planner_produced_plan(second)
        original_apply = target.provisioner.apply

        def reject_delivery(request, snapshot):
            result = original_apply(request, snapshot)
            entry = result.snapshot.entries["provision.node.host"]
            wrong = entry.profile_bindings[0].model_copy(update={"value": {"name": "red"}})
            result.snapshot.entries[entry.address] = replace(entry, profile_bindings=(wrong,))
            return result

        target.provisioner.apply = MethodType(
            lambda self, request, snapshot: reject_delivery(request, snapshot), target.provisioner
        )
        receipt = control.submit_provisioning(second.provisioning)
        assert control.get_operation(receipt.operation_id).state is OperationState.INDETERMINATE
        assert _snapshot_payload(control.snapshot) == before
    recovered = RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "profile-state"))
    assert _snapshot_payload(recovered.snapshot) == before
    assert recovered.get_operation(receipt.operation_id).state is OperationState.INDETERMINATE
    recovered.close()

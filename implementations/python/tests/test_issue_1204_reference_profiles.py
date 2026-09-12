"""Real reference-target profile execution, authentication and durable carriage."""

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.domain_profiles import DomainProfileDefinitionDraftModel, seal_domain_profile_definition
from raes_contracts.realization_structure import realization_constraint_binding
from test_issue_1202_domain_profiles import _admitted, _context, _support
from test_issue_1204_profile_carrier import _profiles


def _reference_profiles(namespace="com.example.private"):
    from raes_contracts.domain_profiles import DomainProfileOperation
    from raes_reference_backend.profile_preparation import RESOURCE_LABEL_SEMANTICS

    authority, _ = _profiles(namespace)
    original = authority.definitions[0].definition
    definition = seal_domain_profile_definition(
        DomainProfileDefinitionDraftModel(
            identity=original.coordinate.model_dump(exclude={"definition_digest"}),
            profile_schema=original.profile_schema,
            semantic_contract=RESOURCE_LABEL_SEMANTICS,
            allowed_contexts=original.allowed_contexts,
        )
    )
    binding = authority.bindings[0].model_copy(update={"coordinate": definition.coordinate})
    document = authority.constraints[0].document.model_copy(
        update={"semantic_profile": definition.coordinate.definition_digest}
    )
    constraint = authority.constraints[0].model_copy(
        update={"document": document, "source_binding": realization_constraint_binding(document, binding.value)}
    )
    authority = authority.model_copy(
        update={"bindings": (binding,), "definitions": (_admitted(definition),), "constraints": (constraint,)}
    )
    context = _context(definition, support_declarations=(_support(definition, *DomainProfileOperation),))
    choices = {definition.coordinate.definition_digest: {"name": "green"}}
    return authority, context, choices


@pytest.mark.parametrize("namespace", ["org.openrae.standard", "com.example.private"])
def test_reference_target_executes_profiles_and_reconciles_without_reselecting(namespace):
    from raes_contracts.planning import ChangeAction
    from raes_reference_backend import create_reference_backend_target
    from raes_reference_backend.drivers.inprocess import InProcessDriver
    from raes_runtime.manager import RuntimeManager

    authority, context, choices = _reference_profiles(namespace)
    driver = InProcessDriver()
    target = create_reference_backend_target(driver=driver, domain_profile_context=context, profile_choices=choices)
    manager = RuntimeManager(target)
    scenario = parse_sdl("name: profiles\nnodes:\n  host: {type: compute}\n")
    execution = manager.plan(scenario, profile_authority=authority)
    assert not [item for item in execution.diagnostics if item.is_error]
    result = manager.apply(execution)
    assert result.success, result.diagnostics
    assert driver.realized_addresses() == {"provision.node.host"}
    assert result.snapshot.entries["provision.node.host"].profile_bindings[0].value == {"name": "green"}
    replanned = manager.plan(scenario, profile_authority=authority)
    assert replanned.provisioning.operations[0].action is ChangeAction.UNCHANGED
    second = manager.apply(replanned)
    assert second.success, second.diagnostics
    assert second.changed_addresses == []
    assert manager.destroy().success
    assert driver.realized_addresses() == set()


def test_reference_profile_support_is_independent_of_time_component():
    from raes_reference_backend import create_reference_backend_target

    _, context, choices = _reference_profiles()
    target = create_reference_backend_target(with_time=False, domain_profile_context=context, profile_choices=choices)
    assert "plan-realization-profiles-v1" in target.manifest.supported_contract_versions
    assert "backend-realization-preparation-v1" in target.manifest.supported_contract_versions


def test_target_registration_checks_pinned_profile_context():
    from raes_reference_backend import create_reference_backend_target

    _, context, choices = _reference_profiles()
    target = create_reference_backend_target(domain_profile_context=context, profile_choices=choices)
    target.provisioner.domain_profile_context = context.model_copy(update={"support_declarations": ()})
    with pytest.raises(ValueError, match="profile"):
        replace(target, name="changed-context")


def test_profile_authentication_and_rejected_delivery_preserve_durable_predecessor(tmp_path):
    from copy import deepcopy

    from raes_contracts.plan_projection import provisioning_plan_model
    from raes_contracts.runtime_state import OperationState
    from raes_reference_backend import create_reference_backend_target
    from raes_runtime.control_plane import RuntimeControlPlane
    from raes_runtime.control_plane_api import create_control_plane_app
    from raes_runtime.control_plane_store_local import LocalControlPlaneStore
    from raes_runtime.control_plane_store_snapshots import _snapshot_payload
    from raes_runtime.manager import RuntimeManager
    from starlette.testclient import TestClient
    from test_runtime_control_plane_api import _test_security

    authority, context, choices = _reference_profiles()
    target = create_reference_backend_target(domain_profile_context=context, profile_choices=choices)
    store = LocalControlPlaneStore(tmp_path / "profile-state")
    control = RuntimeControlPlane(target, store=store)
    scenario = parse_sdl("name: profiles\nnodes:\n  host: {type: compute, resources: {cpu: 1, ram: 1 gib}}\n")
    manager = RuntimeManager(target)
    execution = manager.plan(scenario, profile_authority=authority)
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
        assert target.provisioner._driver.realized_addresses() == set()
        accepted = client.post(
            "/operations/provisioning", json=wire, headers={"authorization": "Bearer test-operator-token"}
        )
        assert accepted.is_success, accepted.text
        receipt = accepted.json()
        assert control.get_operation(receipt["operation_id"]).state is OperationState.SUCCEEDED
    before = _snapshot_payload(control.snapshot)
    second = manager.plan(
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

    # A bound method preserves the target-owned preparation context.
    from types import MethodType

    target.provisioner.apply = MethodType(
        lambda self, request, snapshot: reject_delivery(request, snapshot), target.provisioner
    )
    receipt = control.submit_provisioning(second.provisioning)
    assert control.get_operation(receipt.operation_id).state is OperationState.FAILED
    assert _snapshot_payload(control.snapshot) == before
    control.close()
    recovered = RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path / "profile-state"))
    assert _snapshot_payload(recovered.snapshot) == before
    assert recovered.get_operation(receipt.operation_id).state is OperationState.FAILED
    recovered.close()

"""Adversarial native-boundary checks from the implementation self-review."""

from dataclasses import replace

import pytest
from raes_contracts.runtime_state import RuntimeSnapshot


@pytest.mark.parametrize("mutation", ["outside-constraint", "unowned", "missing", "delete-owner"])
def test_native_reference_rechecks_selected_profile_authority(mutation):
    from raes import parse_sdl
    from raes_reference_backend import create_reference_backend_target
    from raes_reference_backend.drivers.inprocess import InProcessDriver
    from raes_runtime.manager import RuntimeManager
    from test_issue_1204_reference_profiles import _reference_profiles

    authority, context, choices = _reference_profiles()
    driver = InProcessDriver()
    target = create_reference_backend_target(driver=driver, domain_profile_context=context, profile_choices=choices)
    plan = (
        RuntimeManager(target)
        .plan(parse_sdl("name: native\nnodes:\n  host: {type: compute}\n"), profile_authority=authority)
        .provisioning
    )
    prepared = target.provisioner.prepare(plan, RuntimeSnapshot())
    assert prepared.success
    selected = replace(plan, operations=list(prepared.operations))
    if mutation == "unowned":
        selected = replace(selected, profile_authority=None)
    elif mutation == "delete-owner":
        from raes_contracts.planning import ChangeAction

        selected = replace(
            selected,
            realization_constraints=(),
            realization_authority=(),
            operations=[replace(selected.operations[0], action=ChangeAction.DELETE)],
        )
    else:
        op = selected.operations[0]
        bindings = (
            () if mutation == "missing" else (op.profile_bindings[0].model_copy(update={"value": {"name": "outside"}}),)
        )
        selected = replace(selected, operations=[replace(op, profile_bindings=bindings)])
    result = target.provisioner.apply(selected, RuntimeSnapshot())
    assert not result.success
    assert not driver.recorded_ops
    assert any(d.code == "reference-backend.profile-invalid" for d in result.diagnostics)


def test_native_mailbox_rejects_binding_identity_changed_after_preparation():
    from test_issue_1208_profile_selections import _mailbox_case

    _, sink, target, _, execution, driver = _mailbox_case()
    plan = execution.provisioning
    prepared = target.provisioner.prepare(plan, RuntimeSnapshot())
    assert prepared.success
    operations = []
    for op in prepared.operations:
        if op.profile_bindings:
            op = replace(
                op, profile_bindings=(op.profile_bindings[0].model_copy(update={"binding_id": "substituted"}),)
            )
        operations.append(op)
    result = target.provisioner.apply(replace(plan, operations=operations), RuntimeSnapshot())
    assert not result.success
    assert not driver.recorded_ops
    assert not bool(sink._verifiers)


@pytest.mark.parametrize("entrypoint", ["native", "manager"])
def test_failed_operational_readback_does_not_materialize_credentials(monkeypatch, entrypoint):
    from raes_contracts.diagnostics import Diagnostic
    from test_issue_1208_profile_selections import _mailbox_case

    _, sink, target, manager, execution, driver = _mailbox_case()
    previous = RuntimeSnapshot()
    prepared = target.provisioner.prepare(execution.provisioning, previous)
    assert prepared.success
    selected = replace(execution.provisioning, operations=list(prepared.operations))
    monkeypatch.setattr(
        target.provisioner,
        "_observe_selected",
        lambda *args, **kwargs: (
            [Diagnostic("test.readback-failed", "provisioning", "provision.node.mail", "Readback failed.")],
            (),
        ),
    )
    result = target.provisioner.apply(selected, previous) if entrypoint == "native" else manager.apply(execution)
    if entrypoint == "manager":
        from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL, OPERATOR_REFERENCE

        assert FIXTURE_SENTINEL not in repr(result)
        assert OPERATOR_REFERENCE not in repr(result)
        assert any(d.code == "test.readback-failed" for d in result.diagnostics)
    assert not result.success
    assert not bool(sink._verifiers)
    assert driver.realized_addresses()
    assert set(driver.realized_addresses()) <= set(result.snapshot.entries)
    assert set(driver.realized_addresses()) <= set(result.changed_addresses)
    assert result.operational_realization_observations == ()


def test_failed_readback_still_revokes_deleted_mailbox_credentials(monkeypatch):
    from raes import parse_sdl
    from raes_contracts.diagnostics import Diagnostic
    from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL
    from test_issue_1208_profile_selections import _mailbox_case

    binding, sink, target, manager, execution, driver = _mailbox_case()
    initial = manager.apply(execution)
    assert initial.success
    assert sink.authenticates(binding.value["mailbox_ref"], FIXTURE_SENTINEL)
    replacement = manager.plan(parse_sdl("name: replacement\nnodes:\n  other: {type: compute}\n"))
    prepared = target.provisioner.prepare(replacement.provisioning, initial.snapshot)
    assert prepared.success
    selected = replace(replacement.provisioning, operations=list(prepared.operations))
    monkeypatch.setattr(
        target.provisioner,
        "_observe_selected",
        lambda *args, **kwargs: (
            [Diagnostic("test.readback-failed", "provisioning", "provision.node.other", "Readback failed.")],
            (),
        ),
    )
    result = target.provisioner.apply(selected, initial.snapshot)
    assert not result.success
    assert set(result.snapshot.entries) == {"provision.node.other"}
    assert driver.realized_addresses() == frozenset({"provision.node.other"})
    assert not sink.authenticates(binding.value["mailbox_ref"], FIXTURE_SENTINEL)


def test_failed_manager_apply_keeps_value_free_inventory_for_cleanup(monkeypatch):
    from raes import parse_sdl
    from raes_contracts.diagnostics import Diagnostic
    from test_issue_673_account_credential_bindings import FIXTURE_SENTINEL
    from test_issue_1208_profile_selections import _mailbox_case

    binding, sink, target, manager, execution, driver = _mailbox_case()
    assert manager.apply(execution).success
    replacement = manager.plan(parse_sdl("name: replacement\nnodes:\n  other: {type: compute}\n"))
    ordinary_observe = target.provisioner._observe_selected
    monkeypatch.setattr(
        target.provisioner,
        "_observe_selected",
        lambda *args, **kwargs: (
            [Diagnostic("test.readback-failed", "provisioning", "provision.node.other", "Readback failed.")],
            (),
        ),
    )
    result = manager.apply(replacement)
    assert not result.success
    assert any(d.code == "test.readback-failed" for d in result.diagnostics)
    assert not any(d.code == "runtime.backend-contract-invalid" for d in result.diagnostics)
    assert set(driver.realized_addresses()) <= set(result.snapshot.entries)
    assert FIXTURE_SENTINEL not in repr(result)
    monkeypatch.setattr(target.provisioner, "_observe_selected", ordinary_observe)
    assert manager.destroy().success
    assert not driver.realized_addresses()
    assert not sink.authenticates(binding.value["mailbox_ref"], FIXTURE_SENTINEL)


@pytest.mark.parametrize("carrier", ["json", "json-defaults-omitted", "model"])
def test_shared_service_gate_checks_both_supported_profile_carriers(carrier):
    from raes_backend_libvirt.manifest import LIBVIRT_PROVISIONER_CAPABILITIES
    from raes_backend_protocols.service_materialization import service_materialization_plan_diagnostics
    from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp
    from test_issue_1208_profile_selections import _account_profile

    binding, _ = _account_profile(profile_context="service-materialization", address="provision.content.seed")
    value = (
        binding
        if carrier == "model"
        else binding.model_dump(mode="json", exclude_defaults=carrier == "json-defaults-omitted")
    )
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.content.seed",
                resource_type="content-placement",
                payload={"spec": {"service_materialization": value}},
            )
        ]
    )
    diagnostics = service_materialization_plan_diagnostics(plan, LIBVIRT_PROVISIONER_CAPABILITIES, None)
    assert any(d.code == "provisioner.unsupported-service-materialization-profile" for d in diagnostics)
    supported = replace(
        LIBVIRT_PROVISIONER_CAPABILITIES, supported_service_materialization_profiles=frozenset({binding.coordinate})
    )
    assert service_materialization_plan_diagnostics(plan, supported, None) == []

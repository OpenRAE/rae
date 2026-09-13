"""Regression evidence for the authorized second review cycle."""

from dataclasses import replace

import pytest
from raes_contracts.planning import ChangeAction, ProvisionOp
from raes_contracts.profile_selections import authored_resource_profiles
from test_issue_1208_profile_selections import _account_profile, _mailbox_case


def test_default_version_service_binding_retains_direct_plan_authority():
    binding, _ = _account_profile(profile_context="service-materialization", address="provision.content.seed")
    operation = ProvisionOp(
        ChangeAction.CREATE,
        "provision.content.seed",
        "content-placement",
        {"spec": {"service_materialization": binding.model_dump(mode="json", exclude_defaults=True)}},
    )
    assert authored_resource_profiles([operation]) == (binding,)


def test_direct_service_source_rejects_scalar_binding():
    operation = ProvisionOp(
        ChangeAction.CREATE,
        "provision.content.seed",
        "content-placement",
        {"spec": {"service_materialization": "service-content"}},
    )
    with pytest.raises(ValueError):
        authored_resource_profiles([operation])


@pytest.mark.parametrize("carrier", ["mapping", "model"])
@pytest.mark.parametrize("profile", ["service-content", "service-search-index-schema"])
def test_legacy_service_default_is_preserved_without_mutating_input(carrier, profile):
    from copy import deepcopy

    from raes.content import Content, ServiceMaterialization, ServiceSearchIndexSchemaMaterialization

    legacy = {
        "target_service_ref": "nodes.host.services.api",
        "readback_assertion_refs": ["assertions.readback"],
        "evidence_requirement_refs": ["evidence_requirements.result"],
        "observation_boundary_refs": ["observation_boundaries.result"],
        "requirements": {},
    }
    model = ServiceMaterialization
    if profile == "service-search-index-schema":
        legacy.update(interface_profile=profile, requirements={"field_semantics": {"subject": "full-text"}})
        model = ServiceSearchIndexSchemaMaterialization
    original = deepcopy(legacy)
    selection = legacy if carrier == "mapping" else model.model_validate(legacy)
    content = Content.model_validate(
        {
            "type": "dataset" if profile == "service-search-index-schema" else "file",
            "target": "host",
            "path": "/seed",
            "service_materialization": selection,
        }
    )
    assert isinstance(content.service_materialization, model)
    assert content.service_materialization.interface_profile == profile
    assert legacy == original


@pytest.mark.parametrize("include_version", [False, True])
def test_malformed_profile_cannot_fall_back_to_legacy_service_shape(include_version):
    from raes.content import Content
    from raes_backend_libvirt.capability_envelope import capability_envelope_diagnostics
    from raes_backend_libvirt.manifest import LIBVIRT_PROVISIONER_CAPABILITIES
    from raes_backend_protocols.service_materialization import service_materialization_plan_diagnostics
    from raes_contracts.planning import ProvisioningPlan

    binding, _ = _account_profile(profile_context="service-materialization", address="provision.content.seed")
    raw = binding.model_dump(mode="json", exclude_defaults=not include_version)
    raw.pop("coordinate")
    raw["interface_profile"] = "service-content"
    with pytest.raises(ValueError):
        Content.model_validate({"type": "file", "target": "host", "path": "/seed", "service_materialization": raw})
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                ChangeAction.CREATE,
                "provision.content.seed",
                "content-placement",
                {"spec": {"service_materialization": raw}},
            )
        ]
    )
    assert service_materialization_plan_diagnostics(plan, LIBVIRT_PROVISIONER_CAPABILITIES, None)
    assert capability_envelope_diagnostics(plan, LIBVIRT_PROVISIONER_CAPABILITIES)


@pytest.mark.parametrize("ordinary_location", ["same-service", "other-service", "other-node"])
def test_selected_mailbox_does_not_claim_unrelated_inventory(ordinary_location):
    from raes.scenario import Scenario
    from raes_contracts.account_materialization import account_mailbox_materializations
    from test_issue_673_account_credential_bindings import _account_payload

    binding, _, target, manager, _, _ = _mailbox_case()
    account = _account_payload()
    account.update(node="mail", materialization_profile=binding.model_dump(mode="json"))
    selected_service = {
        "mail_service_id": "mail",
        "mailboxes": [{"mailbox_id": "admin", "address": "admin@example.test", "account_ref": "admin"}],
    }
    ordinary = {"mailbox_id": "ordinary", "address": "ordinary@example.test", "status": "disabled"}
    nodes = {"mail": {"type": "compute", "runtime": {"mail_services": [selected_service]}}}
    ordinary_node = "mail"
    if ordinary_location == "same-service":
        selected_service["mailboxes"].append(ordinary)
    else:
        ordinary_service = {
            "mail_service_id": "ordinary-service",
            "mailboxes": [ordinary],
            "components": [{"component_id": "mta", "name": "ordinary-server"}],
        }
        if ordinary_location == "other-service":
            nodes["mail"]["runtime"]["mail_services"].append(ordinary_service)
        else:
            ordinary_node = "other"
            nodes["other"] = {"type": "compute", "runtime": {"mail_services": [ordinary_service]}}
    scenario = Scenario.model_validate({"name": "mixed-mail", "accounts": {"admin": account}, "nodes": nodes})
    execution = manager.plan(scenario)
    prepared = target.provisioner.prepare(execution.provisioning, execution.base_snapshot)
    selected = replace(execution.provisioning, operations=list(prepared.operations))
    requests = account_mailbox_materializations(selected)
    assert [request.mailbox_ref for request in requests] == [binding.value["mailbox_ref"]]
    ordinary_authority = [
        row
        for row in execution.model.realization_authority
        if row.address == f"provision.node.{ordinary_node}" and row.requirement_kind == "runtime-mail-services"
    ]
    assert ordinary_authority
    assert all(row.verification_scope is not None for row in ordinary_authority)


def test_unselected_mail_inventory_creates_no_materialization_request():
    from raes import parse_sdl
    from raes_contracts.account_materialization import account_mailbox_materializations

    _, _, _, manager, _, _ = _mailbox_case()
    scenario = parse_sdl(
        """
name: ordinary-mail
nodes:
  host:
    type: compute
    runtime:
      mail_services:
        - mail_service_id: mail
          mailboxes:
            - {mailbox_id: ordinary, address: ordinary@example.test, status: disabled}
"""
    )
    assert account_mailbox_materializations(manager.plan(scenario).provisioning) == ()

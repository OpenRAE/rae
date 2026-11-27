"""Service-materialization gate checks from the implementation self-review."""

from dataclasses import replace

import pytest


@pytest.mark.parametrize("carrier", ["json", "json-defaults-omitted", "model"])
def test_shared_service_gate_checks_both_supported_profile_carriers(carrier):
    from raes_backend_protocols.service_materialization import service_materialization_plan_diagnostics
    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp
    from test_issue_1208_profile_selections import _account_profile

    capabilities = create_stub_manifest().capabilities.provisioner
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
    diagnostics = service_materialization_plan_diagnostics(plan, capabilities, None)
    assert any(d.code == "provisioner.unsupported-service-materialization-profile" for d in diagnostics)
    supported = replace(capabilities, supported_service_materialization_profiles=frozenset({binding.coordinate}))
    assert service_materialization_plan_diagnostics(plan, supported, None) == []

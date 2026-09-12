"""Nested finite leaf domains remain authoritative through the portable handoff."""

import pytest
from raes import instantiate_scenario, parse_sdl
from raes_contracts.contracts import ProvisioningPlanModel
from raes_contracts.plan_projection import provisioning_plan_model
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane_api_models import _provisioning_plan
from test_issue_1200_mixed_runtime_constraints import _apply, _fixture


@pytest.mark.parametrize("open_collection", [False, True])
def test_nested_version_domain_survives_instantiation_planning_and_runtime(open_collection):
    source = """
name: nested-domains
realization:
  default: closed
  scopes:
    - {field_pointer: /nodes/host/runtime/packages, posture: open}
variables:
  scanner_version:
    type: string
    default: '7.95'
    allowed_values: ['7.94', '7.95']
nodes:
  host:
    type: compute
    runtime:
      packages:
        - {manager: apt, name: nmap, version: '${scanner_version}'}
"""
    _, _, manifest = _fixture({"packages": [{"manager": "apt", "name": "nmap", "version": "7.95"}]})
    if not open_collection:
        source = source.replace(
            "field_pointer: /nodes/host/runtime/packages, posture: open",
            "field_pointer: /nodes/host/runtime/packages, posture: closed",
        )
    scenario = instantiate_scenario(parse_sdl(source))
    model = compile_runtime_model(scenario)
    execution = plan(model, manifest)
    assert execution.is_valid, execution.diagnostics
    portable = _provisioning_plan(
        ProvisioningPlanModel.model_validate_json(
            provisioning_plan_model(execution.provisioning).model_dump_json(),
        )
    )
    authority = next(item for item in portable.realization_authority if item.requirement_kind == "runtime-packages")
    member = authority.constraint_document.root.members[0].constraint
    assert member.fields["version"].domain.values == ["7.94", "7.95"]
    assert member.fields["name"].value == "nmap"
    for version, name, accepted in (
        ("7.94", "nmap", True),
        ("7.95", "nmap", True),
        ("7.96", "nmap", False),
        ("7.94", "curl", False),
    ):
        result = _apply(portable, manifest, {"packages": [{"manager": "apt", "name": name, "version": version}]})
        assert result.success is accepted, result.diagnostics
    additional = _apply(
        portable,
        manifest,
        {
            "packages": [
                {"manager": "apt", "name": "nmap", "version": "7.94"},
                {"manager": "apt", "name": "curl", "version": "8.8"},
            ]
        },
    )
    assert additional.success is open_collection, additional.diagnostics
    if not open_collection:
        assert additional.snapshot.entries == {}
        assert additional.changed_addresses == []
        assert additional.diagnostics[0].code == "runtime.backend-contract-invalid"


def test_classification_owned_domains_do_not_copy_raw_alternatives_into_phase_provenance():
    source = """
name: classified-domain
variables:
  protected_value:
    type: string
    default: selected-fixture-value
    allowed_values: [selected-fixture-value, unselected-fixture-value]
nodes:
  host:
    type: compute
    runtime:
      environment:
        - name: TOKEN
          value: '${protected_value}'
          value_classification: secret_fixture
"""
    scenario = instantiate_scenario(parse_sdl(source))
    assert "unselected-fixture-value" not in scenario.instantiation_provenance.model_dump_json()
    model = compile_runtime_model(scenario)
    _, _, manifest = _fixture({"packages": [{"manager": "apt", "name": "nmap", "version": "7.95"}]})
    execution = plan(model, manifest)
    assert not execution.is_valid
    assert any(diagnostic.code == "realization.authority-bound-unavailable" for diagnostic in execution.diagnostics)

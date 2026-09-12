"""Undefined collection posture is resolved once without losing authored leaves."""

import pytest
from raes import parse_sdl
from raes_contracts.contracts import ProvisioningPlanModel
from raes_contracts.plan_projection import provisioning_plan_model
from raes_contracts.vocabulary import Closure
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane_api_models import _provisioning_plan
from test_issue_1200_mixed_runtime_constraints import _apply, _fixture

_SOURCE = """
name: deferred-closure
realization: {default: unspecified}
nodes:
  host:
    type: compute
    runtime:
      packages: [{manager: apt, name: nmap, version: '7.95'}]
"""


@pytest.mark.parametrize("open_membership", [False, True])
def test_undefined_recursive_collection_uses_one_frozen_apparatus_decision(open_membership):
    _, _, manifest = _fixture({"packages": [{"manager": "apt", "name": "nmap", "version": "7.95"}]})
    scenario = parse_sdl(_SOURCE)
    model = compile_runtime_model(scenario)
    requirement = next(item for item in model.realization_requirements if item.requirement_kind == "runtime-packages")
    assert not requirement.structure_error
    calls = []

    def resolve(requirement, selected):
        assert selected is manifest
        calls.append((requirement.address, requirement.field_path, requirement.requirement_kind))
        return (
            Closure.OPEN_WORLD
            if open_membership and requirement.requirement_kind == "runtime-packages"
            else Closure.CLOSED_WORLD
        )

    execution = plan(model, manifest, apparatus_realization_default=resolve)
    assert execution.is_valid, execution.diagnostics
    assert len(calls) == len(set(calls))
    assert sum(kind == "runtime-packages" for _, _, kind in calls) == 1
    portable = _provisioning_plan(
        ProvisioningPlanModel.model_validate_json(provisioning_plan_model(execution.provisioning).model_dump_json())
    )
    authority = next(item for item in portable.realization_authority if item.requirement_kind == "runtime-packages")
    assert authority.constraint_document is not None
    assert authority.constraint_document.default_closure.posture.value == ("open" if open_membership else "closed")
    member = authority.constraint_document.root.members[0].constraint
    assert member.fields["version"].value == "7.95"
    assert member.fields["version"].origin.value == "author"
    nmap = {"manager": "apt", "name": "nmap", "version": "7.95"}
    assert _apply(portable, manifest, {"packages": [nmap]}).success
    assert not _apply(portable, manifest, {"packages": [{**nmap, "version": "7.94"}]}).success
    assert (
        _apply(portable, manifest, {"packages": [nmap, {"manager": "apt", "name": "curl", "version": "8.0"}]}).success
        is open_membership
    )


def test_pending_source_cannot_be_materialized_as_unconstrained_authority():
    from raes_processor.planner.realization_authority_materialization import materialize_realization_authority

    _, _, manifest = _fixture({"packages": [{"manager": "apt", "name": "nmap", "version": "7.95"}]})
    model = compile_runtime_model(parse_sdl(_SOURCE))
    authorities, diagnostics = materialize_realization_authority(model, manifest)
    assert diagnostics
    assert not any(authority.requirement_kind == "runtime-packages" for authority in authorities)

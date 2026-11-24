"""Selected switch families keep absent node identity absent through planning."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from issue_1629_trial_fixture import TrialServices
from raes import admit_scenario_family, instantiate_scenario, parse_sdl, select_scenario_family
from raes._errors import SDLSelectionError
from raes.canonical import InstantiatedScenarioSnapshot, canonical_instantiated_sdl_bytes
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts.contracts import ProvisioningPlanModel
from raes_contracts.contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.planner import plan, realization_authority_diagnostics
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_api_models import _provisioning_plan
from test_issue_1866_node_identity_absence import _request_with_processor, _trial_from_request

_SWITCH = "provision.network.lan"
_COMPUTE = "provision.node.primary"
_IDENTITY_KINDS = ("os-family", "os-distribution", "os-version", "node-architecture")
_EMPTY_IDENTITY = [
    pytest.param({"os": None}, id="os-null"),
    pytest.param({"os_distribution": None}, id="distribution-null"),
    pytest.param({"os_version": ""}, id="version-empty"),
    pytest.param({"architecture": None}, id="architecture-null"),
    pytest.param(
        {"os": None, "os_distribution": None, "os_version": "", "architecture": None}, id="all-identity-empty"
    ),
]


def _family(switch=None, compute=None):
    nodes = {"lan": {"type": "switch", **(switch or {})}}
    if compute is not None:
        nodes["primary"] = {"type": "compute", "os": "linux", **compute}
    return admit_scenario_family(
        parse_sdl(json.dumps({"name": "switch-selection", "realization": {"default": "closed"}, "nodes": nodes}))
    )


def _snapshot(scenario):
    return InstantiatedScenarioSnapshot.model_validate_json(canonical_instantiated_sdl_bytes(scenario)).scenario


def _portable(provisioning):
    restored = _provisioning_plan(
        ProvisioningPlanModel.model_validate_json(provisioning_plan_model(provisioning).model_dump_json())
    )
    assert runtime_plan_digest(restored) == runtime_plan_digest(provisioning)
    return restored


def _authority(provisioning, address):
    return {entry.requirement_kind: entry for entry in provisioning.realization_authority if entry.address == address}


def _planned(scenario, manifest):
    execution = plan(compile_scenario_runtime_model(scenario), manifest)
    assert execution.is_valid, [(item.code, item.message) for item in execution.diagnostics]
    return execution.provisioning


def _passes_pre_apply(scenario, manifest):
    provisioning = _planned(scenario, manifest)
    assert realization_authority_diagnostics(provisioning, manifest) == []
    restored = _portable(provisioning)
    assert realization_authority_diagnostics(restored, manifest) == []
    return provisioning


def test_unchanged_selected_switch_family_passes_pre_apply_authority():
    family = _family()
    manifest = create_stub_manifest()
    direct = _passes_pre_apply(instantiate_scenario(family), manifest)
    selected_scenario = select_scenario_family(family, {})

    for scenario in (selected_scenario, _snapshot(selected_scenario)):
        selected = _passes_pre_apply(scenario, manifest)
        assert _authority(selected, _SWITCH) == _authority(direct, _SWITCH)
        assert not any(
            record.model_path.startswith("nodes.lan.") and record.model_path != "nodes.lan.type"
            for record in scenario.instantiation_provenance.explicitness
        )


@pytest.mark.parametrize("identity", _EMPTY_IDENTITY)
def test_supplied_empty_switch_identity_is_an_omission(identity):
    manifest = create_stub_manifest()
    omitted = _passes_pre_apply(instantiate_scenario(_family()), manifest)
    family = _family(switch=identity)

    for scenario in (instantiate_scenario(family), select_scenario_family(family, {})):
        for current in (scenario, _snapshot(scenario)):
            supplied = _passes_pre_apply(current, manifest)
            assert _authority(supplied, _SWITCH) == _authority(omitted, _SWITCH)
            assert all(_authority(supplied, _SWITCH)[kind].constraint_document is None for kind in _IDENTITY_KINDS)


def test_switch_identity_cannot_carry_a_value():
    with pytest.raises(Exception, match="compute-only fields: os_distribution"):
        _family(switch={"os_distribution": "ubuntu"})


@pytest.mark.parametrize(
    "compute,committed",
    [
        pytest.param({}, set(), id="omitted"),
        pytest.param(
            {"os_distribution": None, "architecture": None}, {"os-distribution", "node-architecture"}, id="null"
        ),
        pytest.param(
            {"os_distribution": "ubuntu", "architecture": "x86_64"},
            {"os-distribution", "node-architecture"},
            id="explicit",
        ),
    ],
)
def test_selection_keeps_compute_identity_commitments_equal_to_direct(compute, committed):
    family = _family(compute=compute)
    direct = compile_scenario_runtime_model(instantiate_scenario(family))
    selected_scenario = select_scenario_family(family, {})

    for scenario in (selected_scenario, _snapshot(selected_scenario)):
        selected = compile_scenario_runtime_model(scenario)
        assert selected.realization_authority == direct.realization_authority
        assert selected.realization_requirements == direct.realization_requirements
        bound = {
            requirement.requirement_kind
            for requirement in selected.realization_requirements
            if requirement.address == _COMPUTE and requirement.constraint_document is not None
        }
        assert bound & {"os-distribution", "node-architecture"} == committed


@pytest.mark.parametrize("substitution", ["value", "binding"])
def test_selected_switch_plan_still_rejects_changed_authority(substitution):
    _, target, realized = _switch_trial({}, compute={"os_distribution": "ubuntu", "architecture": "x86_64"})
    provisioning = deepcopy(realized.execution_plan.provisioning)
    assert realization_authority_diagnostics(provisioning, target.manifest) == []
    assert _authority(provisioning, _COMPUTE)["os-distribution"].constraint_document is not None
    if substitution == "value":
        operation = next(item for item in provisioning.operations if item.address == _COMPUTE)
        operation.payload["os_distribution"] = "debian"
    else:
        provisioning = replace(
            provisioning,
            realization_authority=tuple(
                replace(item, constraint_binding="sha256:" + "0" * 64)
                if item.address == _COMPUTE and item.requirement_kind == "os-distribution"
                else item
                for item in provisioning.realization_authority
            ),
        )

    assert [item.code for item in realization_authority_diagnostics(provisioning, target.manifest)] == [
        "realization.authority-selection-invalid"
    ]


def test_selection_refuses_a_modified_omitted_default():
    family = _family(compute={})
    family.nodes["primary"].features["mutated"] = "after-admission"

    with pytest.raises(SDLSelectionError, match="modified omitted default"):
        select_scenario_family(family, {})


def _switch_trial(identity, compute=None):
    source = {
        "name": "compiler-family",
        "nodes": {
            "primary": {"type": "compute", "os": "linux", **(compute or {})},
            "lan": {"type": "switch", **identity},
        },
        "infrastructure": {
            "primary": {"count": 1, "links": ["lan"]},
            "lan": {"count": 1, "properties": {"cidr": "10.0.0.0/24", "gateway": "10.0.0.1"}},
        },
    }
    request = _request_with_processor().with_family(admit_scenario_family(parse_sdl(json.dumps(source))))
    return _trial_from_request(request, target_name="switch")


@pytest.mark.parametrize("identity", [pytest.param({}, id="omitted"), *_EMPTY_IDENTITY])
def test_admitted_trial_with_switch_passes_public_runtime_admission(identity):
    inputs, target, realized = _switch_trial(identity)
    provisioning = realized.execution_plan.provisioning
    assert realization_authority_diagnostics(provisioning, target.manifest) == []
    assert realization_authority_diagnostics(_portable(provisioning), target.manifest) == []
    assert all(_authority(provisioning, _SWITCH)[kind].constraint_document is None for kind in _IDENTITY_KINDS)

    services = TrialServices(target)
    with RuntimeControlPlane(target) as runtime:
        assert runtime.admit_experiment(inputs, services=services)
        assert services.live == {}

"""Scenario selection preserves omitted and authored capability authority."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from raes import admit_scenario_family, instantiate_scenario, parse_sdl, select_scenario_family
from raes.canonical import InstantiatedScenarioSnapshot, canonical_instantiated_sdl_bytes, canonical_sdl_bytes
from raes.scenario import ExpandedScenario, InstantiatedScenario
from raes_backend_protocols.capabilities import OperatingSystemCompatibility
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.contracts import ExperimentSelectionMemberOutcomeModel, LiteralBindingValueModel
from raes_contracts.explicitness import ExplicitnessClass
from raes_contracts.planning import RealizationAuthorityMode
from raes_contracts.realization_structure import RealizationRelationStatus, evaluate_realization_constraint
from raes_contracts.vocabulary import ObservationStrength, RealizationSupportMode, RealizationVerificationScope
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.planner import plan
from raes_processor.semantics.realization_concerns import project_realization_concern, realization_concern_descriptors
from test_issue_1066_runtime_resource_limits import _supporting_manifest


def _payload() -> dict:
    return {
        "name": "omitted-capabilities",
        "realization": {"default": "open"},
        "nodes": {
            "node": {
                "type": "compute",
                "runtime": {
                    "environment": [
                        {
                            "name": "MODE",
                            "value": "fixture",
                            "value_classification": "plain",
                            "provenance": "runtime",
                            "source": "fixture",
                        }
                    ]
                },
            }
        },
    }


def _family(payload: dict) -> ExpandedScenario:
    return admit_scenario_family(parse_sdl(json.dumps(payload)))


def _requirement(scenario: InstantiatedScenario):
    return next(
        requirement
        for requirement in compile_scenario_runtime_model(scenario).realization_requirements
        if requirement.requirement_kind == "linux-capabilities"
    )


def _round_trip(scenario: InstantiatedScenario) -> InstantiatedScenario:
    return InstantiatedScenarioSnapshot.model_validate_json(canonical_instantiated_sdl_bytes(scenario)).scenario


@pytest.mark.parametrize("selection", ["none", "parameter", "inventory", "empty-inventory"])
def test_selection_preserves_omitted_capabilities(selection: str) -> None:
    payload = _payload()
    outcomes = {}
    if selection == "parameter":
        payload["variables"] = {"mode": {"type": "string", "default": "fixture"}}
        payload["nodes"]["node"]["runtime"]["environment"][0]["value"] = "${mode}"
        payload["variation_points"] = {
            "mode": {
                "kind": "parameter",
                "target": {"kind": "variable", "variable": "mode"},
                "domain": {"kind": "enum", "values": ["fixture", "selected"]},
            }
        }
        outcomes = {"mode": LiteralBindingValueModel(kind="literal", value="selected")}
    elif selection in {"inventory", "empty-inventory"}:
        payload["nodes"]["node"]["runtime"]["scheduled_jobs"] = [{"scheduled_job_id": "job"}]
        payload["variation_points"] = {
            "jobs": {
                "kind": "alternative",
                "target": {"kind": "structural", "owner": "node", "slot": "nodes.runtime.scheduled_jobs"},
                "alternatives": {
                    "chosen": {
                        "kind": "runtime-inventory",
                        "references": []
                        if selection == "empty-inventory"
                        else ["nodes.node.runtime.scheduled_jobs.job"],
                    }
                },
            }
        }
        outcomes = {"jobs": ExperimentSelectionMemberOutcomeModel(kind="member", member_id="chosen")}
    baseline = deepcopy(payload)
    baseline.pop("variation_points", None)
    direct = _requirement(instantiate_scenario(_family(baseline)))
    family = _family(payload)
    before = canonical_sdl_bytes(family)

    selected = select_scenario_family(family, outcomes)
    requirement = _requirement(selected)

    assert direct.explicitness is ExplicitnessClass.OPEN
    assert not direct.structure_error
    assert requirement == direct
    assert not any(
        "linux_capabilities" in record.model_path for record in selected.instantiation_provenance.explicitness
    )
    assert canonical_sdl_bytes(family) == before


def test_selected_capabilities_survive_snapshot_and_planning() -> None:
    family = _family(_payload())
    manifest = _supporting_manifest(mode=RealizationSupportMode.OPEN_REALIZATION)
    kinds = frozenset(descriptor.concern_kind for descriptor in realization_concern_descriptors())
    support = replace(
        manifest.realization_support[0],
        support_mode=RealizationSupportMode.OPEN_REALIZATION,
        supported_constraint_kinds=manifest.realization_support[0].supported_constraint_kinds | kinds,
        supported_exact_requirement_kinds=manifest.realization_support[0].supported_exact_requirement_kinds | kinds,
        observation_capabilities={
            kind: RealizationObservationCapability(
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=ObservationStrength.GUEST_OBSERVED,
            )
            for kind in kinds
        },
    )
    manifest = replace(
        manifest,
        realization_support=(support,),
        capabilities=replace(
            manifest.capabilities,
            provisioner=replace(
                manifest.provisioner,
                operating_systems=(OperatingSystemCompatibility("linux", "ubuntu", frozenset({"22.04"})),),
            ),
        ),
    )
    direct = instantiate_scenario(family)
    selected = select_scenario_family(family, {})
    for label, scenario in (
        ("direct", direct),
        ("direct snapshot", _round_trip(direct)),
        ("selected", selected),
        ("selected snapshot", _round_trip(selected)),
    ):
        model = compile_scenario_runtime_model(scenario)
        result = plan(model, manifest)

        assert result.is_valid, (label, [(diagnostic.code, diagnostic.message) for diagnostic in result.diagnostics])
        assert not any(
            diagnostic.code == "realization.authority-bound-unavailable" for diagnostic in result.diagnostics
        )
        authority = next(
            authority
            for authority in result.provisioning.realization_authority
            if authority.requirement_kind == "linux-capabilities"
        )
        assert authority.mode is RealizationAuthorityMode.OPEN
        assert _requirement(scenario) == _requirement(direct)


@pytest.mark.parametrize("policy", [{}, {"required": []}, {"required": ["CAP_NET_ADMIN"]}])
def test_selection_preserves_authored_capability_constraints(policy: dict) -> None:
    payload = _payload()
    payload["nodes"]["node"]["runtime"]["linux_capabilities"] = policy
    family = _family(payload)
    direct = _requirement(instantiate_scenario(family))
    selected = select_scenario_family(family, {})

    for scenario in (selected, _round_trip(selected)):
        requirement = _requirement(scenario)
        assert requirement == direct
        assert not requirement.structure_error
        assert requirement.constraint_document is not None
        authored = project_realization_concern("linux-capabilities", policy, recursive=True)
        assert evaluate_realization_constraint(requirement.constraint_document, authored).status is (
            RealizationRelationStatus.CONFORMANT
        )
        if policy.get("required"):
            weakened = project_realization_concern("linux-capabilities", {"required": []}, recursive=True)
            assert evaluate_realization_constraint(requirement.constraint_document, weakened).status is (
                RealizationRelationStatus.NONCONFORMANT
            )


def test_selection_preserves_authored_null_capabilities() -> None:
    payload = _payload()
    payload["nodes"]["node"]["runtime"]["linux_capabilities"] = None
    family = _family(payload)
    direct = _requirement(instantiate_scenario(family))
    selected = _requirement(select_scenario_family(family, {}))

    assert direct.explicitness is ExplicitnessClass.EXACT
    assert direct.structure_error
    assert selected == direct

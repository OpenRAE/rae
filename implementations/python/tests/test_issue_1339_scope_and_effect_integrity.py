"""Canonical scope identities survive compilation; registered effects cannot bypass eligibility."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from raes import SDLInstantiationError, SDLValidationError, instantiate_scenario, parse_sdl, parse_sdl_file
from raes._declarations import build_declaration_index
from raes._reference_targetability import ReferencePurpose, declaration_eligible
from raes_processor.compiler import compile_scenario_runtime_model
from test_act_617_mixed_control import _scenario_yaml
from test_dsl_142_participant_inject_delivery import _scenario_yaml as _delivery_yaml
from test_issue_1338_identity_authority import _autonomous_payload
from test_issue_1339_reference_eligibility import _payload
from test_issue_1339_relationship_endpoints import matrix_payload
from test_participant_interactive_access import _scenario, _two_access_bindings


def _parse(payload):
    return parse_sdl(yaml.safe_dump(payload, sort_keys=False))


def _compose(tmp_path: Path, payload: dict):
    module = deepcopy(payload)
    module["module"] = {
        "id": "example/scope-and-effects",
        "version": "1.0.0",
        "exports": {
            key: list(value) for key, value in module.items() if isinstance(value, dict) and key != "variables"
        },
    }
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(module, sort_keys=False), encoding="utf-8")
    root = {"name": "root", "imports": [{"path": "module.yaml", "namespace": name} for name in ("first", "second")]}
    path = tmp_path / "root.yaml"
    path.write_text(yaml.safe_dump(root), encoding="utf-8")
    return parse_sdl_file(path)


@pytest.mark.parametrize("reference", ["web", "nodes.web"])
@pytest.mark.parametrize("composed", [False, True])
def test_authority_scope_projects_the_node_selected_by_validation_despite_a_same_named_service(
    tmp_path: Path, reference: str, composed: bool
) -> None:
    payload = _payload()
    payload["nodes"]["web"]["services"][0]["name"] = "web"
    payload["relationships"]["link"]["target"] = "nodes.web.services.web"
    payload["behavior_specifications"]["red-behavior"]["authority_scope_refs"] = [reference]
    scenario = _compose(tmp_path, payload) if composed else _parse(payload)
    model = compile_scenario_runtime_model(scenario)
    for prefix in ("first.", "second.") if composed else ("",):
        spec = model.behavior_specifications[f"participant.behavior-specification.{prefix}red-behavior"]
        node = next(item for item in model.node_deployments.values() if item.node_name == f"{prefix}web")
        assert spec.authority_scope_addresses == (node.address,)
        assert spec.authority_scope_refs == tuple(
            scenario.behavior_specifications[f"{prefix}red-behavior"].authority_scope_refs
        )


def test_semantic_only_authority_scopes_keep_their_authored_identities_without_runtime_projection() -> None:
    payload = _payload()
    refs = ["agents.blue", "entities.org", "relationships.link"]
    payload["behavior_specifications"]["red-behavior"]["authority_scope_refs"] = refs
    spec = compile_scenario_runtime_model(_parse(payload)).behavior_specifications[
        "participant.behavior-specification.red-behavior"
    ]
    assert spec.authority_scope_refs == tuple(refs)
    assert spec.authority_scope_addresses == ()


def test_compiled_resource_and_delivery_scopes_keep_their_runtime_addresses() -> None:
    payload = matrix_payload()
    refs = [
        *(f"generated_artifacts.{name}" for name in payload["generated_artifacts"]),
        *(f"persistent_volumes.{name}" for name in payload["persistent_volumes"]),
        "behavior_specifications.red-briefing.participant_inject_deliveries.briefing",
    ]
    payload["behavior_specifications"]["projection-check"] = {
        "semantic_version": "1.0.0",
        "behavior_mode": "policy-directed",
        "participant_refs": ["red-agent"],
        "authority_scope_refs": refs,
    }
    model = compile_scenario_runtime_model(_parse(payload))
    scope = model.behavior_specifications["participant.behavior-specification.projection-check"]
    assert scope.authority_scope_refs == tuple(refs)
    expected = {
        item.address
        for group in (model.generated_artifacts, model.persistent_volumes, model.participant_inject_deliveries)
        for item in group.values()
    }
    assert set(scope.authority_scope_addresses) == expected


def test_section_typed_interactive_bindings_keep_their_node_and_account_when_other_kinds_share_the_names() -> None:
    payload = yaml.safe_load(_scenario(access=_two_access_bindings()))
    payload["entities"]["workstation"] = {"role": "blue"}
    payload["entities"]["operator"] = {"role": "blue"}
    model = compile_scenario_runtime_model(_parse(payload))
    participant = model.participant_behaviors["participant.behavior.blue-participant"]
    assert all(access.target_address == "provision.node.workstation" for access in participant.interactive_access)
    account = next(item for item in model.account_placements.values() if item.account_name == "operator")
    assert all(access.account_address == account.address for access in participant.interactive_access)


def test_delivery_item_projection_uses_the_targetable_domain_beside_a_same_named_support_record() -> None:
    payload = yaml.safe_load(_delivery_yaml())
    payload.setdefault("workflows", {})["briefing"] = {"start": "finish", "steps": {"finish": {"type": "end"}}}
    spec = payload["behavior_specifications"]["red-briefing"]
    binding = spec["participant_inject_deliveries"]["briefing"]
    binding["source_item_ref"] = "briefing"
    binding["result_item_ref"] = "briefing"
    model = compile_scenario_runtime_model(_parse(payload))
    delivery = next(iter(model.participant_inject_deliveries.values()))
    assert delivery.source_item_address == delivery.result_item_address == "provision.content.briefing"


def test_autonomous_effect_projection_uses_the_action_target_domain_beside_a_same_named_objective() -> None:
    payload, _participant = _autonomous_payload()
    payload["objectives"]["customer-portal"] = deepcopy(payload["objectives"]["goal"])
    payload["action_contracts"]["probe-customer-portal-login"]["effects"][0]["target_refs"] = ["customer-portal"]
    model = compile_scenario_runtime_model(_parse(payload))
    node = next(item for item in model.node_deployments.values() if item.node_name == "customer-portal")
    execution = model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution
    assert node.address in execution.target_addresses


def _mixed_scope_payload(kind: str, bare: bool) -> tuple[dict, str]:
    payload = yaml.safe_load(_scenario_yaml())
    if kind == "service":
        payload["nodes"]["web"]["services"] = [{"name": "http", "port": 80}]
        local, canonical = "http", "nodes.web.services.http"
    elif kind == "subnet":
        payload["nodes"]["lan"] = {"type": "switch"}
        payload["infrastructure"] = {"lan": {"count": 1}}
        local, canonical = "lan", "infrastructure.lan"
    else:
        payload["content"] = {"briefing": {"type": "file", "target": "web", "path": "/opt/brief", "text": "brief"}}
        local, canonical = "briefing", "content.briefing"
    for agent in payload["agents"].values():
        agent["operating_scope"] = [local if bare else canonical]
    behavior = payload["behavior_specifications"]["controlled-red"]
    behavior["authority_scope_refs"] = [canonical]
    for state in behavior["mixed_control"]["controller_states"].values():
        state["scope_refs"] = [canonical]
    return payload, canonical


@pytest.mark.parametrize("kind", ["service", "subnet", "content"])
@pytest.mark.parametrize("bare", [False, True])
def test_mixed_control_compares_scope_identities_using_each_fields_own_resolver(kind: str, bare: bool) -> None:
    payload, canonical = _mixed_scope_payload(kind, bare)
    model = compile_scenario_runtime_model(_parse(payload))
    spec = model.behavior_specifications["participant.behavior-specification.controlled-red"]
    assert all(state.scope_refs == (canonical,) for state in spec.controller_states)
    for participant in model.participant_behaviors.values():
        assert participant.operating_scope_addresses
        assert participant.operating_scope_addresses == spec.authority_scope_addresses


def test_mixed_control_scope_still_refuses_widening_and_controller_scope_mismatch() -> None:
    payload, _canonical = _mixed_scope_payload("service", True)
    payload["behavior_specifications"]["controlled-red"]["mixed_control"]["controller_states"]["supervised"][
        "scope_refs"
    ] = ["nodes.internal"]
    with pytest.raises(SDLValidationError, match="widens.*authority scope"):
        _parse(payload)
    payload["behavior_specifications"]["controlled-red"]["authority_scope_refs"].append("nodes.internal")
    with pytest.raises(SDLValidationError, match="outside controller"):
        _parse(payload)


@pytest.mark.parametrize(
    "reference",
    ["workflows.response.steps.validate", "outcome_interpretation_rules.scan-outcome", "nodes.dc.roles.ops"],
)
@pytest.mark.parametrize("stage", ["authored", "composed", "instantiated"])
def test_nonreferenceable_declarations_cannot_be_opaque_effect_targets(
    tmp_path: Path, reference: str, stage: str
) -> None:
    payload = matrix_payload()
    effect = payload["action_contracts"]["scan"]["effects"][0]
    if stage == "instantiated":
        effect["target_refs"] = ["${effect_target}"]
        payload.setdefault("variables", {})["effect_target"] = {"type": "string", "default": "nodes.app"}
        scenario = _parse(payload)
        with pytest.raises(SDLInstantiationError, match="eligible as an action target"):
            instantiate_scenario(scenario, parameters={"effect_target": reference})
    else:
        effect["target_refs"] = [reference]
        with pytest.raises(SDLValidationError, match="eligible as an action target"):
            _compose(tmp_path, payload) if stage == "composed" else _parse(payload)


def test_the_scenario_declaration_cannot_be_an_opaque_effect_target() -> None:
    payload = matrix_payload()
    payload["action_contracts"]["scan"]["effects"][0]["target_refs"] = [f"scenario.{payload['name']}"]
    with pytest.raises(SDLValidationError, match="eligible as an action target"):
        _parse(payload)


def test_every_registered_kind_obeys_effect_eligibility_and_genuine_boundary_tokens_remain_opaque() -> None:
    payload = matrix_payload()
    index = build_declaration_index(_parse(payload))
    for declaration in index.declarations:
        candidate = deepcopy(payload)
        candidate["action_contracts"]["scan"]["effects"][0]["target_refs"] = [declaration.address]
        if declaration_eligible(declaration, ReferencePurpose.ACTION_TARGET):
            _parse(candidate)
        else:
            with pytest.raises(SDLValidationError, match="eligible as an action target"):
                _parse(candidate)
    payload["action_contracts"]["scan"]["effects"][0]["target_refs"] = ["external_boundary_token", "nodes.undeclared"]
    compiled = compile_scenario_runtime_model(_parse(payload))
    assert compiled.action_contracts["participant.action-contract.scan"].spec["effects"][0]["target_refs"] == [
        "external_boundary_token",
        "nodes.undeclared",
    ]

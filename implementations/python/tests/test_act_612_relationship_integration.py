"""Participant relationship composition, control binding and published shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from raes import SDLInstantiationError, SDLParseError, SDLValidationError, instantiate_scenario, parse_sdl_file
from raes.language_service import language_completions, language_references
from raes_processor.compiler import compile_scenario_runtime_model
from test_act_612_participant_relationships import KINDS, _parse, _payload, _refined_payload
from test_act_617_mixed_control import _scenario_yaml

ROOT = Path(__file__).resolve().parents[3]


def test_published_relationship_fixtures() -> None:
    root = ROOT / "contracts/fixtures/sdl/participant-relationships-v1"
    model = compile_scenario_runtime_model(parse_sdl_file(root / "valid/abstract-relations.yaml"))
    assert {edge["participant"]["kind"] for edge in model.relationship_specs.values()} == set(KINDS)
    with pytest.raises(SDLValidationError, match="participant endpoint"):
        parse_sdl_file(root / "invalid/entity-endpoint.yaml")


@pytest.mark.parametrize("kind", ["supervision", "delegation"])
def test_control_binding_reuses_existing_policy_and_direction(kind: str) -> None:
    payload = yaml.safe_load(_scenario_yaml())
    endpoints = ("supervisor-agent", "red-agent") if kind == "supervision" else ("red-agent", "supervisor-agent")
    payload["relationships"] = {
        "control": {
            "type": "participant",
            "source": endpoints[0],
            "target": endpoints[1],
            "participant": {"kind": kind, "control_specification_ref": "behavior_specifications.controlled-red"},
        }
    }
    model = compile_scenario_runtime_model(_parse(payload))
    policy = model.behavior_specifications["participant.behavior-specification.controlled-red"]
    assert policy.mixed_control_participant_address == "participant.behavior.red-agent"
    assert len(policy.control_transitions) == 2
    payload["relationships"]["control"]["source"], payload["relationships"]["control"]["target"] = endpoints[::-1]
    with pytest.raises(SDLValidationError, match="control_specification_ref.*direction"):
        _parse(payload)


def test_control_binding_cannot_select_plain_behavior_or_unavailable_policy() -> None:
    payload = _refined_payload("supervision")
    detail = payload["relationships"]["work"]["participant"]
    for ref, message in (("missing", "declared behavior_specifications"), ("pair", "mixed_control")):
        detail["control_specification_ref"] = ref
        with pytest.raises(SDLValidationError, match=message):
            _parse(payload)


def _import_twice(tmp_path: Path, payload: dict):
    payload["module"] = {
        "id": "example/participants",
        "version": "1.0.0",
        "exports": {key: list(value) for key, value in payload.items() if isinstance(value, dict)},
    }
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(payload))
    (tmp_path / "root.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "imported-pairs",
                "imports": [{"path": "module.yaml", "namespace": name} for name in ("first", "second")],
            }
        )
    )
    return compile_scenario_runtime_model(parse_sdl_file(tmp_path / "root.yaml"))


def test_composition_rewrites_all_refinements_and_keeps_copies_separate(tmp_path: Path) -> None:
    model = _import_twice(tmp_path, _refined_payload())
    for namespace in ("first", "second"):
        edge = model.relationship_specs[f"{namespace}.work"]
        assert edge["source"] == f"agents.{namespace}.alice"
        assert edge["target"] == f"{namespace}.bob"
        assert edge["participant"]["source_action_refs"] == [f"action_contracts.{namespace}.alice-action"]
        assert edge["participant"]["target_action_refs"] == [f"{namespace}.bob-action"]
        assert edge["participant"]["scope_refs"] == [f"nodes.{namespace}.workspace"]
        assert edge["participant"]["authority_basis_refs"] == [f"{namespace}.team-a"]
        assert edge["participant"]["behavior_specification_refs"] == [f"behavior_specifications.{namespace}.pair"]
        assert edge["participant"]["observation_boundary_refs"] == [f"{namespace}.shared-view"]


def test_composition_preserves_control_policy_identity(tmp_path: Path) -> None:
    payload = yaml.safe_load(_scenario_yaml())
    payload["relationships"] = {
        "control": {
            "type": "participant",
            "source": "supervisor-agent",
            "target": "red-agent",
            "participant": {
                "kind": "supervision",
                "control_specification_ref": "behavior_specifications.controlled-red",
            },
        }
    }
    model = _import_twice(tmp_path, payload)
    for namespace in ("first", "second"):
        edge = model.relationship_specs[f"{namespace}.control"]
        assert edge["participant"]["control_specification_ref"] == f"behavior_specifications.{namespace}.controlled-red"
        policy = model.behavior_specifications[f"participant.behavior-specification.{namespace}.controlled-red"]
        assert policy.mixed_control_participant_address == f"participant.behavior.{namespace}.red-agent"


@pytest.mark.parametrize(
    ("field", "aliases"),
    [
        ("source_action_refs", ["alice-action", "action_contracts.alice-action"]),
        ("target_action_refs", ["bob-action", "action_contracts.bob-action"]),
        ("behavior_specification_refs", ["pair", "behavior_specifications.pair"]),
        ("observation_boundary_refs", ["shared-view", "observation_boundaries.shared-view"]),
    ],
)
def test_section_refinements_reject_repeated_canonical_aliases(field: str, aliases: list[str]) -> None:
    payload = _refined_payload()
    payload["relationships"]["work"]["participant"][field] = aliases
    with pytest.raises(SDLValidationError, match="repeats a canonical reference"):
        _parse(payload)


@pytest.mark.parametrize(
    ("field", "aliases"),
    [
        ("authority_basis_refs", ["team-a", "entities.team-a"]),
        ("scope_refs", ["workspace", "nodes.workspace"]),
    ],
)
@pytest.mark.parametrize("parameterized", [False, True])
def test_named_refinements_reject_repeated_canonical_aliases(
    field: str, aliases: list[str], parameterized: bool
) -> None:
    payload = _refined_payload()
    if parameterized:
        payload["variables"] = {"alias": {"type": "string", "default": aliases[1]}}
        aliases = [aliases[0], "${alias}"]
    payload["relationships"]["work"]["participant"][field] = aliases
    if parameterized:
        authored = _parse(payload)
        with pytest.raises(SDLInstantiationError, match=field + ".*repeats a canonical reference"):
            instantiate_scenario(authored)
    else:
        with pytest.raises(SDLValidationError, match=field + ".*repeats a canonical reference"):
            _parse(payload)


def test_language_navigation_tracks_typed_action_refinement() -> None:
    payload = _refined_payload()
    result = language_references(yaml.safe_dump(payload), "action_contracts.alice-action")
    assert any(item["path"] == "/relationships/work/participant/source_action_refs/0" for item in result["occurrences"])


def test_authority_refinement_completion_includes_non_targetable_anchors() -> None:
    payload = _refined_payload()
    payload["workflows"] = {"mandate": {"start": "done", "steps": {"done": {"type": "end"}}}}
    payload["agents"]["alice"]["authority_anchors"] = ["workflows.mandate"]
    payload["relationships"]["work"]["participant"]["authority_basis_refs"] = ["workflows.mandate"]
    _parse(payload)
    result = language_completions(
        yaml.safe_dump(payload), cursor_path="/relationships/work/participant/authority_basis_refs"
    )
    assert any(item["detail"] == "workflows.mandate" for item in result["items"])


def test_endpoint_variable_is_checked_again_after_instantiation() -> None:
    payload = _payload()
    payload["variables"] = {"peer": {"type": "string", "default": "bob", "allowed_values": ["bob", "alice", "team-a"]}}
    payload["relationships"]["work"]["target"] = "${peer}"
    authored = _parse(payload)
    assert instantiate_scenario(authored).relationships["work"].target == "bob"
    for value in ("alice", "team-a"):
        with pytest.raises(SDLInstantiationError):
            instantiate_scenario(authored, parameters={"peer": value})


def test_role_based_refinement_defers_variable_entity_until_instantiation() -> None:
    payload = _refined_payload()
    payload["variables"] = {"identity": {"type": "string", "default": "team-a", "allowed_values": ["team-a", "team-b"]}}
    payload["agents"]["alice"]["affiliations"] = ["${identity}"]
    behavior = payload["behavior_specifications"]["pair"]
    behavior["participant_refs"] = []
    behavior["participant_role_refs"] = ["red"]
    authored = _parse(payload)
    instantiate_scenario(authored)
    with pytest.raises(SDLInstantiationError, match="relationship endpoint"):
        instantiate_scenario(authored, parameters={"identity": "team-b"})


@pytest.mark.parametrize("kind", KINDS)
def test_published_authoring_schema_accepts_each_abstract_relationship(kind: str) -> None:
    schema = json.loads((ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    Draft202012Validator(schema).validate(_payload(kind))


@pytest.mark.parametrize("refs", [[""], ["  "], ["alice-action", "alice-action"]])
def test_invalid_reference_lists_fail_at_shape_boundary(refs: list[str]) -> None:
    payload = _payload()
    payload["relationships"]["work"]["participant"]["source_action_refs"] = refs
    with pytest.raises(SDLParseError):
        _parse(payload)


@pytest.mark.parametrize(
    "mutation", ["missing", "wrong-type", "properties", "other-detail", "blank-ref", "duplicate-ref"]
)
def test_published_schema_enforces_participant_shape(mutation: str) -> None:
    payload = _payload()
    relation = payload["relationships"]["work"]
    if mutation == "missing":
        del relation["participant"]
    elif mutation == "wrong-type":
        relation["type"] = "manages"
    elif mutation == "properties":
        relation["properties"] = {"grant": "administrator"}
    elif mutation == "other-detail":
        relation["domain_controller"] = {}
    else:
        relation["participant"]["source_action_refs"] = ["  "] if mutation == "blank-ref" else ["act", "act"]
    schema = json.loads((ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(payload))


def test_coordination_refinement_cannot_point_interaction_at_another_participant() -> None:
    payload = _refined_payload()
    payload["agents"]["third"] = {"affiliations": ["team-a"], "actions": ["bob-action"]}
    payload["action_contracts"]["alice-action"]["interactions"][0]["target"] = "agents.third"
    with pytest.raises(SDLValidationError, match="coordination.*action interaction"):
        _parse(payload)


def test_coordination_may_target_a_shared_resource_without_fabricated_peer_target() -> None:
    payload = _refined_payload()
    payload["action_contracts"]["alice-action"]["interactions"][0]["target"] = "nodes.workspace"
    _parse(payload)


def test_published_schema_restricts_control_binding_to_control_relationships() -> None:
    payload = _payload("cooperation")
    payload["relationships"]["work"]["participant"]["control_specification_ref"] = "policy"
    schema = json.loads((ROOT / "contracts/schemas/sdl/sdl-authoring-input-v1.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(payload))


def test_ambiguous_bare_participant_name_requires_qualification() -> None:
    payload = _payload()
    payload["entities"]["bob"] = {"role": "white"}
    with pytest.raises(SDLValidationError, match="participant endpoint.*unambiguously"):
        _parse(payload)
    payload["relationships"]["work"]["target"] = "agents.bob"
    _parse(payload)


@pytest.mark.parametrize("kind", ["cooperation", "competition"])
def test_objective_refinement_preserves_declared_intent_and_rejects_unrelated_owner(kind: str) -> None:
    payload = _payload(kind)
    payload["propositions"] = {
        "role-present": {
            "description": "The participant's entity has a declared role.",
            "subjects": ["entities.team-a"],
            "basis": "declared_state",
            "predicate": {
                "kind": "presence",
                "property": "role",
                "semantic_ref": "urn:raes:declared-property:entity-role",
                "operator": "exists",
            },
        }
    }
    payload["assertions"] = {"declared": {"proposition": "role-present", "role": "postcondition"}}
    payload["objectives"] = {"work-goal": {"assigned_participant": "alice", "success": {"assertions": ["declared"]}}}
    payload["relationships"]["work"]["participant"]["objective_refs"] = ["objectives.work-goal"]
    model = compile_scenario_runtime_model(_parse(payload))
    assert model.relationship_specs["work"]["participant"]["objective_refs"] == ["objectives.work-goal"]
    payload["agents"]["third"] = {"affiliations": ["team-b"]}
    payload["objectives"]["work-goal"]["assigned_participant"] = "third"
    with pytest.raises(SDLValidationError, match="objective_refs.*relationship endpoint"):
        _parse(payload)


def test_objective_assignment_refinement_revalidates_parameterized_assignment():
    payload = _payload("cooperation")
    payload["variables"] = {"assignee": {"type": "string", "default": "alice", "allowed_values": ["alice", "third"]}}
    payload["agents"]["third"] = {"affiliations": ["team-a"]}
    payload["propositions"] = {
        "role-present": {
            "description": "The participant entity has a declared role.",
            "subjects": ["entities.team-a"],
            "basis": "declared_state",
            "predicate": {
                "kind": "presence",
                "property": "role",
                "semantic_ref": "urn:raes:declared-property:entity-role",
                "operator": "exists",
            },
        }
    }
    payload["assertions"] = {"declared": {"proposition": "role-present", "role": "postcondition"}}
    payload["objectives"] = {
        "work-goal": {"owner": "team-a", "assigned_participant": "${assignee}", "success": {"assertions": ["declared"]}}
    }
    payload["relationships"]["work"]["participant"]["objective_refs"] = ["objectives.work-goal"]
    authored = _parse(payload)
    instantiate_scenario(authored)
    with pytest.raises(SDLInstantiationError, match="objective_refs.*relationship endpoint"):
        instantiate_scenario(authored, parameters={"assignee": "third"})


def test_relationship_scope_cannot_widen_selected_control_policy():
    payload = yaml.safe_load(_scenario_yaml())
    for participant in payload["agents"].values():
        participant["operating_scope"].append("nodes.internal")
    payload["relationships"] = {
        "control": {
            "type": "participant",
            "source": "supervisor-agent",
            "target": "red-agent",
            "participant": {
                "kind": "supervision",
                "scope_refs": ["nodes.web"],
                "control_specification_ref": "controlled-red",
            },
        }
    }
    _parse(payload)
    payload["relationships"]["control"]["participant"]["scope_refs"] = ["nodes.internal"]
    with pytest.raises(SDLValidationError, match="control_specification_ref.*scope"):
        _parse(payload)

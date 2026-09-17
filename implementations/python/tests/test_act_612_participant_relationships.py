"""ACT-612 authored participant relationships and optional refinements."""

from __future__ import annotations

import pytest
import yaml
from raes import SDLParseError, SDLValidationError, parse_sdl
from raes_processor.compiler import compile_scenario_runtime_model

KINDS = ("coordination", "delegation", "cooperation", "competition", "supervision")


def _payload(kind: str = "coordination") -> dict:
    return {
        "name": "abstract-participant-relationships",
        "entities": {"team-a": {"role": "red"}, "team-b": {"role": "blue"}},
        "agents": {"alice": {"entity": "team-a"}, "bob": {"entity": "team-b"}},
        "relationships": {
            "work": {
                "type": "participant",
                "source": "agents.alice",
                "target": "bob",
                "participant": {"kind": kind},
            }
        },
    }


def _parse(payload: dict):
    return parse_sdl(yaml.safe_dump(payload))


@pytest.mark.parametrize("kind", KINDS)
def test_abstract_relationship_preserves_intent_without_invented_detail(kind: str) -> None:
    scenario = _parse(_payload(kind))
    relation = scenario.relationships["work"]
    assert relation.participant.kind.value == kind
    assert (relation.source, relation.target) == ("agents.alice", "bob")
    model = compile_scenario_runtime_model(scenario)
    assert model.relationship_specs["work"]["participant"]["kind"] == kind
    assert set(model.relationship_specs) == {"work"}  # No inferred reciprocal edge.
    assert not model.node_deployments
    assert not model.action_contracts
    assert not model.behavior_specifications
    assert not model.observation_boundaries
    assert not model.observation_demands
    assert not model.capture_demands
    for participant in model.participant_behaviors.values():
        assert not participant.authority_anchor_refs
        assert not participant.operating_scope_refs
        assert not participant.action_contract_addresses


@pytest.mark.parametrize("endpoint", ["source", "target"])
@pytest.mark.parametrize("ref", ["team-a", "entities.team-a", "absent"])
def test_relationship_endpoints_must_be_participants(endpoint: str, ref: str) -> None:
    payload = _payload()
    payload["relationships"]["work"][endpoint] = ref
    with pytest.raises(SDLValidationError, match="participant endpoint"):
        _parse(payload)


def test_relationship_endpoints_must_be_distinct_after_alias_resolution() -> None:
    payload = _payload()
    payload["relationships"]["work"]["target"] = "alice"
    with pytest.raises(SDLValidationError, match="distinct participants"):
        _parse(payload)


@pytest.mark.parametrize("mutation", ["missing", "wrong-type", "properties", "other-detail"])
def test_participant_detail_has_one_typed_owner(mutation: str) -> None:
    payload = _payload()
    relation = payload["relationships"]["work"]
    if mutation == "missing":
        del relation["participant"]
    elif mutation == "wrong-type":
        relation["type"] = "manages"
    elif mutation == "properties":
        relation["properties"] = {"grant": "administrator"}
    else:
        relation["domain_controller"] = {}
    with pytest.raises(SDLParseError, match="participant"):
        _parse(payload)


def _refined_payload(kind: str = "coordination") -> dict:
    payload = _payload(kind)
    payload["nodes"] = {"workspace": {"type": "compute"}, "outside": {"type": "compute"}}
    for name in ("alice", "bob"):
        payload["agents"][name].update(
            actions=[name + "-action"],
            authority_anchors=["entities.team-a"],
            operating_scope=["workspace"],
            observation_boundaries=["shared-view"],
        )
    payload["action_contracts"] = {
        name + "-action": {
            "semantic_version": "1.0.0",
            "behavioral_granularity": "atomic",
            "procedure_basis": "abstract state transition",
            "realization_profile": "abstract",
            "fidelity_claim": "declared transition only",
            "preconditions": [
                {
                    "precondition_id": "authorized",
                    "precondition_class": "authority",
                    "description": "declared authority",
                }
            ],
            "effects": [
                {"effect_id": "no-change", "effect_class": "no_effect", "description": "abstract synchronization"}
            ],
            "failure_classes": ["authority_denied", "unknown"],
        }
        for name in ("alice", "bob")
    }
    payload["action_contracts"]["alice-action"]["interactions"] = [
        {
            "interaction_class": "coordination",
            "target": "agents.bob",
            "rationale": "synchronize the declared transitions",
            "related_actions": ["bob-action"],
        }
    ]
    payload["observation_boundaries"] = {
        "shared-view": {
            "projection_basis": "declared shared state",
            "observable_refs": ["nodes.workspace"],
            "redaction_policy": "hide private state",
            "latency_profile": "immediate",
        }
    }
    payload["behavior_specifications"] = {
        "pair": {
            "semantic_version": "1.0.0",
            "participant_refs": ["alice", "bob"],
            "action_contract_refs": ["alice-action", "bob-action"],
        }
    }
    payload["relationships"]["work"]["participant"].update(
        source_action_refs=["action_contracts.alice-action"],
        target_action_refs=["bob-action"],
        behavior_specification_refs=["behavior_specifications.pair"],
        authority_basis_refs=["team-a"],
        scope_refs=["nodes.workspace"],
        observation_boundary_refs=["shared-view"],
    )
    return payload


def test_selected_refinements_resolve_and_survive_compilation() -> None:
    payload = _refined_payload()
    model = compile_scenario_runtime_model(_parse(payload))
    compiled = model.relationship_specs["work"]["participant"]
    for field, expected in payload["relationships"]["work"]["participant"].items():
        assert compiled[field] == expected


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_action_refs", ["bob-action"], "source_action_refs.*available to.*alice"),
        ("target_action_refs", ["alice-action"], "target_action_refs.*available to.*bob"),
        ("objective_refs", ["missing"], "objective_refs.*declared objectives"),
        ("behavior_specification_refs", ["missing"], "behavior_specification_refs.*declared behavior_specifications"),
        ("authority_basis_refs", ["team-b"], "authority_basis_refs.*source authority"),
        ("scope_refs", ["outside"], "scope_refs.*operating_scope"),
        ("observation_boundary_refs", ["missing"], "observation_boundary_refs.*declared observation_boundaries"),
    ],
)
def test_explicit_refinements_are_binding(field: str, value: list, message: str) -> None:
    payload = _refined_payload()
    payload["relationships"]["work"]["participant"][field] = value
    with pytest.raises(SDLValidationError, match=message):
        _parse(payload)


def test_coordination_refinement_requires_existing_action_agreement() -> None:
    payload = _refined_payload()
    payload["action_contracts"]["alice-action"]["interactions"] = []
    with pytest.raises(SDLValidationError, match="coordination.*action interaction"):
        _parse(payload)


def test_unselected_observation_does_not_become_visible() -> None:
    payload = _refined_payload("supervision")
    payload["agents"]["alice"]["observation_boundaries"] = []
    with pytest.raises(SDLValidationError, match="observation_boundary_refs.*source participant"):
        _parse(payload)


def test_refinement_cannot_bind_an_unrelated_behavior() -> None:
    payload = _refined_payload()
    payload["agents"]["third"] = {"entity": "team-a"}
    payload["behavior_specifications"]["pair"]["participant_refs"] = ["third"]
    with pytest.raises(SDLValidationError, match="behavior_specification_refs.*relationship endpoint"):
        _parse(payload)

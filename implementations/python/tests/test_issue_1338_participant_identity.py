"""Identity, affiliation and objective assignment agree across SDL stages."""

from __future__ import annotations

import pytest
import yaml
from raes import SDLParseError, SDLValidationError, parse_sdl
from raes_processor.compiler import compile_scenario_runtime_model


def _parse(payload: dict):
    return parse_sdl(yaml.safe_dump(payload))


def _action() -> dict:
    return {
        "semantic_version": "1.0.0",
        "behavioral_granularity": "atomic",
        "procedure_basis": "abstract transition",
        "realization_profile": "abstract",
        "fidelity_claim": "declared transition only",
        "preconditions": [
            {"precondition_id": "authorized", "precondition_class": "authority", "description": "explicit grant"}
        ],
        "effects": [{"effect_id": "unchanged", "effect_class": "no_effect", "description": "no state change"}],
        "failure_classes": ["authority_denied", "unknown"],
    }


def _payload() -> dict:
    return {
        "name": "identity-assignment",
        "entities": {"team": {"role": "red"}},
        "agents": {
            "one": {"affiliations": ["team"], "actions": ["observe"]},
            "two": {"affiliations": ["team"]},
        },
        "action_contracts": {"observe": _action()},
        "propositions": {
            "ready": {
                "description": "The authored subject is ready.",
                "subjects": ["agents.one"],
                "basis": "declared_state",
                "predicate": {
                    "kind": "boolean",
                    "property": "ready",
                    "semantic_ref": "urn:raes:declared-property:ready",
                    "operator": "equals",
                    "expected": True,
                },
            }
        },
        "assertions": {"done": {"proposition": "ready", "role": "postcondition"}},
        "objectives": {"goal": {"owner": "team", "success": {"assertions": ["done"]}}},
    }


def test_composite_identity_needs_no_affiliation_or_components() -> None:
    model = compile_scenario_runtime_model(_parse({"name": "composite", "agents": {"harness": {}}}))
    assert set(model.participant_behaviors) == {"participant.behavior.harness"}
    participant = model.participant_behaviors["participant.behavior.harness"]
    assert participant.participant_name == "harness"
    assert participant.affiliation_names == ()
    assert participant.role == ""
    assert not model.entity_specs
    assert not model.node_deployments


def test_affiliations_are_normalized_separately_from_objective_relations():
    from raes.semantics.participant_behavior import analyze_participant_affiliations

    scenario = _parse(_payload())
    analysis = analyze_participant_affiliations(
        agents_by_name=scenario.agents, entity_names=set(scenario.entities), is_unresolved=lambda _: False
    )
    assert not analysis.issues
    assert [(ref.participant_name, ref.reference_kind, ref.canonical_name) for ref in analysis.references] == [
        ("one", "affiliation", "team"),
        ("two", "affiliation", "team"),
    ]


def test_realized_actor_record_does_not_rewrite_authored_assignment():
    from raes_contracts.contracts.participant_runtime import ParticipantBehaviorHistoryEventModel

    payload = _payload()
    payload["objectives"]["goal"]["assigned_participant"] = "one"
    scenario = _parse(payload)
    before = scenario.model_dump(mode="json")
    runtime = compile_scenario_runtime_model(scenario)
    event = ParticipantBehaviorHistoryEventModel(
        event_type="action_attempted",
        timestamp="2026-09-21T12:00:00Z",
        participant_address="participant.behavior.two",
        episode_id="second-episode",
        action_instance_id="observed-action",
        actor_provenance="participant.behavior.two",
    )
    assert event.participant_address != runtime.objectives["evaluation.objective.goal"].assigned_participant_address
    assert event.actor_provenance == "participant.behavior.two"
    assert scenario.model_dump(mode="json") == before
    assert "owner_name" not in type(event).model_fields


@pytest.mark.parametrize(
    "relations,valid",
    [
        ({}, False),
        ({"owner": None}, False),
        ({"owner": "team"}, True),
        ({"assigned_participant": "one"}, True),
        ({"owner": "team", "assigned_participant": "one"}, True),
        ({"agent": "one"}, False),
    ],
)
def test_objective_schema_and_model_share_relation_shape(relations, valid):
    from jsonschema import Draft202012Validator
    from raes.objectives import Objective

    validator = Draft202012Validator(Objective.model_json_schema())
    payload = {**relations, "success": {"assertions": ["done"]}}
    assert validator.is_valid(payload) is valid


def test_shared_affiliation_does_not_merge_identity_or_assign_objectives() -> None:
    payload = _payload()
    payload["objectives"]["goal"]["assigned_participant"] = "one"
    payload["objectives"]["goal"]["actions"] = ["observe"]
    model = compile_scenario_runtime_model(_parse(payload))
    assert set(model.participant_behaviors) == {"participant.behavior.one", "participant.behavior.two"}
    objective = model.objectives["evaluation.objective.goal"]
    assert objective.owner_name == "team"
    assert objective.assigned_participant_name == "one"
    assert objective.assigned_participant_address == "participant.behavior.one"
    assert not hasattr(objective, "actor_type")
    assert not hasattr(objective, "actor_name")
    assert model.participant_behaviors["participant.behavior.one"].affiliation_names == ("team",)


def test_unassigned_owner_constraints_are_intent_without_participant() -> None:
    payload = _payload()
    payload.pop("agents")
    payload["propositions"]["ready"]["subjects"] = ["entities.team"]
    payload["objectives"]["goal"]["actions"] = ["observe"]
    model = compile_scenario_runtime_model(_parse(payload))
    assert not model.participant_behaviors
    objective = model.objectives["evaluation.objective.goal"]
    assert objective.owner_name == "team"
    assert objective.assigned_participant_name == ""
    assert objective.assigned_participant_address == ""


@pytest.mark.parametrize("assigned", [None, "one"])
def test_objective_actions_always_require_declared_contracts(assigned: str | None) -> None:
    payload = _payload()
    payload["objectives"]["goal"].update(actions=["invented"])
    if assigned:
        payload["objectives"]["goal"]["assigned_participant"] = assigned
        payload["agents"][assigned]["actions"] = ["invented"]
    with pytest.raises(SDLValidationError, match="action.*declared action_contract"):
        _parse(payload)


def test_assignment_requires_the_selected_participants_action() -> None:
    payload = _payload()
    payload["objectives"]["goal"].update(assigned_participant="two", actions=["observe"])
    with pytest.raises(SDLValidationError, match="action.*not.*declared.*two"):
        _parse(payload)


@pytest.mark.parametrize("field", ["owner", "assigned_participant"])
def test_dangling_objective_relations_are_rejected(field: str) -> None:
    payload = _payload()
    payload["objectives"]["goal"][field] = "absent"
    with pytest.raises(SDLValidationError, match="undefined"):
        _parse(payload)


@pytest.mark.parametrize("assignment", [None, "one", "third"])
def test_relationship_objective_membership_requires_endpoint_assignment(assignment: str | None) -> None:
    payload = _payload()
    payload["agents"]["third"] = {"affiliations": ["team"]}
    payload["relationships"] = {
        "pair": {
            "type": "participant",
            "source": "one",
            "target": "two",
            "participant": {"kind": "cooperation", "objective_refs": ["goal"]},
        }
    }
    if assignment:
        payload["objectives"]["goal"]["assigned_participant"] = assignment
    if assignment == "one":
        _parse(payload)
    else:
        with pytest.raises(SDLValidationError, match="objective_refs.*assigned.*endpoint"):
            _parse(payload)


@pytest.mark.parametrize(
    ("affiliations", "role", "expected"),
    [
        ([], None, ""),
        (["team"], None, "red"),
        (["team"], "blue", "blue"),
        (["team", "other"], None, ""),
        (["team", "other"], "green", "green"),
    ],
)
def test_effective_role_has_one_explicit_compatibility_rule(affiliations, role, expected) -> None:
    payload = {
        "name": "roles",
        "entities": {"team": {"role": "red"}, "other": {"role": "blue"}},
        "agents": {"subject": {"affiliations": affiliations, "role": role}},
    }
    model = compile_scenario_runtime_model(_parse(payload))
    assert model.participant_behaviors["participant.behavior.subject"].role == expected


def test_role_selection_compiles_only_matching_effective_roles() -> None:
    payload = _payload()
    payload["agents"]["one"]["role"] = "blue"
    payload["behavior_specifications"] = {
        "blue-behavior": {
            "semantic_version": "1.0.0",
            "participant_role_refs": ["blue"],
            "action_contract_refs": ["observe"],
        }
    }
    model = compile_scenario_runtime_model(_parse(payload))
    behavior = model.behavior_specifications["participant.behavior-specification.blue-behavior"]
    assert behavior.participant_addresses == ("participant.behavior.one",)


@pytest.mark.parametrize("affiliations", [["missing"], ["team", "team"]])
def test_affiliations_require_distinct_declared_entities(affiliations) -> None:
    payload = _payload()
    payload["agents"]["one"]["affiliations"] = affiliations
    with pytest.raises(SDLValidationError, match="affiliation"):
        _parse(payload)


def test_legacy_fields_have_explicit_migration_guidance() -> None:
    with pytest.raises(SDLParseError, match="migrate_participant_identity"):
        _parse({"name": "old", "agents": {"one": {"entity": "team"}}})
    payload = _payload()
    payload["objectives"]["goal"] = {"entity": "team", "success": {"assertions": ["done"]}}
    with pytest.raises(SDLParseError, match="migrate_participant_identity"):
        _parse(payload)

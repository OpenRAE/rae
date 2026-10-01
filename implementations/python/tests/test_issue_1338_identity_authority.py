"""Ownership and affiliation never widen autonomous evaluation authority."""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml
from raes import SDLValidationError
from test_dsl_437_benign_participant_execution import _scenario_yaml
from test_issue_1338_participant_identity import _parse, _payload


def _autonomous_payload():
    payload = yaml.safe_load(_scenario_yaml())
    for agent in payload["agents"].values():
        if "entity" in agent:
            agent["affiliations"] = [agent.pop("entity")]
    participant = next(iter(payload["agents"]))
    minimal = _payload()
    payload["propositions"]["ready"] = minimal["propositions"]["ready"]
    payload["propositions"]["ready"]["subjects"] = [f"agents.{participant}"]
    payload["assertions"]["done"] = minimal["assertions"]["done"]
    payload["objectives"] = {"goal": {"owner": "enterprise-participant", "success": {"assertions": ["done"]}}}
    return payload, participant


def test_owner_affiliation_does_not_assign_non_evaluated_participant():
    payload, participant = _autonomous_payload()
    _parse(payload)
    payload["objectives"]["goal"]["assigned_participant"] = participant
    with pytest.raises(SDLValidationError, match="non-evaluated.*objective"):
        _parse(payload)


@pytest.mark.parametrize("assignment", [None, "other", "selected"])
def test_declared_objective_authority_requires_assignment_to_selected_participant(assignment):
    payload, participant = _autonomous_payload()
    payload["agents"]["other"] = {"affiliations": ["enterprise-participant"], "role": "blue"}
    if assignment:
        payload["objectives"]["goal"]["assigned_participant"] = participant if assignment == "selected" else "other"
    policy = payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]
    policy["evaluation_authority"] = {"mode": "declared", "objective_refs": ["goal"]}
    if assignment == "selected":
        _parse(payload)
    else:
        with pytest.raises(SDLValidationError, match="objective.*assigned"):
            _parse(payload)


def test_explicit_role_controls_autonomous_role_check():
    payload, participant = _autonomous_payload()
    payload["agents"][participant]["role"] = "red"
    with pytest.raises(SDLValidationError, match="must have the green role"):
        _parse(payload)


@pytest.mark.parametrize("selection", ["explicit", "role", "mixed"])
def test_autonomous_ownership_conflicts_include_role_selected_participants(selection):
    payload, participant = _autonomous_payload()
    payload["agents"]["peer"] = deepcopy(payload["agents"][participant])
    specs = payload["behavior_specifications"]
    first = specs["participant-behavior"]
    second = specs["peer-behavior"] = deepcopy(first)
    first["participant_refs"] = [participant]
    first["participant_role_refs"] = []
    second["participant_refs"] = ["peer"]
    second["participant_role_refs"] = []
    _parse(payload)  # Independent explicit owners are valid.
    if selection == "explicit":
        second["participant_refs"].append(participant)
    elif selection == "role":
        first["participant_role_refs"] = ["green"]
        second["participant_role_refs"] = ["green"]
    else:
        second["participant_role_refs"] = ["green"]
    with pytest.raises(SDLValidationError, match="already controlled by behavior specification"):
        _parse(payload)

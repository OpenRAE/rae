"""Participant relations retain their meaning through imports and author tools."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from raes import SDLInstantiationError, SDLValidationError, instantiate_scenario, parse_sdl_file
from raes.language_service import language_completions, language_references
from raes_processor.compiler import compile_scenario_runtime_model
from test_issue_1338_participant_identity import _parse, _payload


def test_inspection_labels_owner_and_assignment_without_actor_inference():
    from raes_mcp.tools.inspection._references import _build_reference_map
    from raes_mcp.tools.inspection._summary import _build_summary
    from test_issue_1338_participant_identity import _parse, _payload

    payload = _payload()
    payload["objectives"]["goal"]["assigned_participant"] = "one"
    payload["objectives"]["goal"]["actions"] = ["observe"]
    scenario = _parse(payload)
    text = _build_summary(scenario)
    assert "owner=team" in text
    assert "assigned_participant=one" in text
    assert "actor=" not in text
    refs = _build_reference_map(scenario)
    assert set(refs[("agents", "one")]) == {"team"}
    assert {"team", "one", "observe"} <= set(refs[("objectives", "goal")])


def test_imports_preserve_identity_affiliation_assignment_and_action_constraints(tmp_path: Path) -> None:
    payload = _payload()
    payload["objectives"]["goal"].update(assigned_participant="one", actions=["observe"])
    payload["module"] = {
        "id": "example/identity",
        "version": "1.0.0",
        "exports": {key: list(value) for key, value in payload.items() if isinstance(value, dict)},
    }
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(payload))
    (tmp_path / "root.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "two-copies",
                "imports": [{"path": "module.yaml", "namespace": name} for name in ("first", "second")],
            }
        )
    )
    model = compile_scenario_runtime_model(parse_sdl_file(tmp_path / "root.yaml"))
    for namespace in ("first", "second"):
        objective = model.objectives[f"evaluation.objective.{namespace}.goal"]
        assert objective.owner_name == f"{namespace}.team"
        assert objective.assigned_participant_address == f"participant.behavior.{namespace}.one"
        assert objective.spec["actions"] == [f"{namespace}.observe"]
        participant = model.participant_behaviors[f"participant.behavior.{namespace}.one"]
        assert participant.affiliation_names == (f"{namespace}.team",)
        assert participant.role == "red"


def test_parameterized_roles_and_assignments_are_revalidated() -> None:
    payload = _payload()
    payload["variables"] = {
        "team": {"type": "string", "default": "team"},
        "role": {"type": "string", "default": "blue"},
        "assignee": {"type": "string", "default": "one"},
    }
    payload["agents"]["one"].update(affiliations=["${team}"], role="${role}")
    payload["objectives"]["goal"].update(assigned_participant="${assignee}", actions=["observe"])
    authored = _parse(payload)
    model = compile_scenario_runtime_model(authored)
    assert model.participant_behaviors["participant.behavior.one"].role == "blue"
    for parameters in ({"team": "missing"}, {"role": "operator"}, {"assignee": "two"}):
        with pytest.raises(SDLInstantiationError):
            instantiate_scenario(authored, parameters=parameters)


@pytest.mark.parametrize(("field", "symbol"), [("owner", "entities.team"), ("assigned_participant", "agents.one")])
def test_editor_relations_use_their_own_reference_sections(field, symbol) -> None:
    payload = _payload()
    payload["objectives"]["goal"]["assigned_participant"] = "one"
    text = yaml.safe_dump(payload)
    result = language_completions(text, cursor_path=f"/objectives/goal/{field}")
    details = {item["detail"] for item in result["items"]}
    assert symbol in details
    assert ("agents.one" if field == "owner" else "entities.team") not in details
    references = language_references(text, symbol=symbol)
    assert any(item["path"] == f"/objectives/goal/{field}" for item in references["occurrences"])


def test_affiliation_editor_navigation_is_not_participant_identity() -> None:
    text = yaml.safe_dump(_payload())
    references = language_references(text, symbol="entities.team")
    assert any(item["path"] == "/agents/one/affiliations/0" for item in references["occurrences"])


def test_entity_does_not_gain_participant_relationship_semantics() -> None:
    payload = _payload()
    payload["relationships"] = {
        "pair": {
            "type": "participant",
            "source": "entities.team",
            "target": "one",
            "participant": {"kind": "cooperation"},
        }
    }
    with pytest.raises(SDLValidationError, match="participant endpoint"):
        _parse(payload)


@pytest.mark.parametrize(("slot", "candidate"), [("owner", "team"), ("assigned_participant", "one")])
def test_variation_slots_use_distinct_owner_and_assignment_kinds(slot, candidate):
    payload = _payload()
    payload["variation_points"] = {
        "relation": {
            "kind": "governed-reference",
            "target": {"kind": "reference", "owner": "goal", "slot": f"objectives.{slot}"},
            "domain": {"kind": "governed-reference", "authority": "inventory-v1", "allowed_refs": [candidate]},
        }
    }
    scenario = _parse(payload)
    assert scenario.variation_points["relation"].target.slot.value == f"objectives.{slot}"
    payload["variation_points"]["relation"]["domain"]["allowed_refs"] = ["one" if slot == "owner" else "team"]
    with pytest.raises(SDLValidationError):
        _parse(payload)

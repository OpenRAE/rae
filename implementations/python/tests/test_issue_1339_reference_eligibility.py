"""Reference purposes admit explicit declaration kinds at every SDL stage (#1339)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from raes import SDLInstantiationError, SDLValidationError, instantiate_scenario, parse_sdl, parse_sdl_file
from raes import _reference_targetability as policy
from raes._declarations import build_declaration_index
from raes._module_symbols import HASHMAP_SECTIONS
from raes_processor.compiler import compile_scenario_runtime_model

_PROPOSITION = {
    "description": "The web host is ready.",
    "subjects": ["nodes.web"],
    "basis": "declared_state",
    "predicate": {
        "kind": "boolean",
        "property": "ready",
        "semantic_ref": "urn:raes:declared-property:ready",
        "operator": "equals",
        "expected": True,
    },
}

# Reference fields by purpose, as paths into _payload().
FIELDS = {
    "objective": ("objectives", "goal", "targets"),
    "interaction": ("action_contracts", "probe", "interactions", 0, "target"),
    "shared-state": ("action_contracts", "probe", "interactions", 0, "shared_state_refs"),
    "effect": ("action_contracts", "probe", "effects", 0, "target_refs"),
    "authority-scope": ("behavior_specifications", "red-behavior", "authority_scope_refs"),
}


def _payload() -> dict:
    """One declaration of every category that a purpose admits or refuses."""

    return deepcopy(
        {
            "name": "reference-eligibility",
            "nodes": {
                "web": {
                    "type": "compute",
                    "resources": {"ram": "1 GiB", "cpu": 1},
                    "services": [{"name": "http", "port": 80}],
                }
            },
            "entities": {"org": {"role": "blue"}},
            "conditions": {"alive": {"command": "true", "interval": 5}},
            "injects": {"notice": {"from_entity": "org", "to_entities": ["org"]}},
            "propositions": {"ready": _PROPOSITION},
            "assertions": {"done": {"proposition": "ready", "role": "postcondition"}},
            "relationships": {"link": {"type": "connects_to", "source": "web", "target": "nodes.web.services.http"}},
            "action_contracts": {
                "probe": {
                    "semantic_version": "1.0.0",
                    "behavioral_granularity": "atomic",
                    "procedure_basis": "abstract transition",
                    "realization_profile": "abstract",
                    "fidelity_claim": "declared transition only",
                    "preconditions": [
                        {"precondition_id": "authorized", "precondition_class": "authority", "description": "grant"}
                    ],
                    "effects": [
                        {
                            "effect_id": "touch",
                            "effect_class": "intended_effect",
                            "description": "the declared object changes",
                            "target_refs": ["nodes.web"],
                        }
                    ],
                    "failure_classes": ["authority_denied", "unknown"],
                    "interactions": [
                        {
                            "interaction_class": "shared_state_change",
                            "target": "nodes.web",
                            "rationale": "the action writes declared web state",
                            "shared_state_refs": ["nodes.web"],
                        }
                    ],
                }
            },
            "observation_boundaries": {
                "view": {
                    "projection_basis": "participant-local projection",
                    "observable_refs": ["nodes.web"],
                    "redaction_policy": "hidden refs never project",
                    "latency_profile": "immediate",
                    "view_rules": [
                        {
                            "information_ref": "nodes.web",
                            "boundary_class": "observable_resource",
                            "disposition": "observable",
                            "visibility_basis": "declared",
                        }
                    ],
                }
            },
            "agents": {"red": {"actions": ["probe"], "observation_boundaries": ["view"]}, "blue": {}},
            "behavior_specifications": {
                "red-behavior": {
                    "semantic_version": "1.0.0",
                    "lifecycle_state": "active",
                    "participant_refs": ["red"],
                    "action_contract_refs": ["probe"],
                    "observation_boundary_refs": ["view"],
                    "authority_scope_refs": ["nodes.web"],
                    "behavior_mode": "policy-directed",
                }
            },
            "objectives": {"goal": {"owner": "org", "targets": ["nodes.web"], "success": {"assertions": ["done"]}}},
        }
    )


def _set(payload: dict, path: tuple, value: str) -> dict:
    node = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = [value] if isinstance(node[path[-1]], list) else value
    return payload


def _parse(payload: dict):
    return parse_sdl(yaml.safe_dump(payload))


def test_every_indexed_section_and_runtime_family_has_an_explicit_decision() -> None:
    decided = policy.DECLARATION_CATEGORIES.keys() | policy.UNREFERENCEABLE_KINDS
    section_kinds = {policy.section_declaration_kind(section) for section in HASHMAP_SECTIONS}

    assert sorted(section_kinds - decided) == []
    assert {policy.DECLARATION_CATEGORIES[kind] for kind in policy.RUNTIME_INVENTORY_KINDS} == {
        policy.DeclarationCategory.RESOURCE
    }


def test_an_unclassified_kind_is_eligible_for_nothing_and_cannot_register(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not any(policy.is_eligible("future_declaration_kind", purpose) for purpose in policy.ReferencePurpose)
    scenario = _parse(_payload())
    undecided = {kind: category for kind, category in policy.DECLARATION_CATEGORIES.items() if kind != "conditions"}
    monkeypatch.setattr(policy, "DECLARATION_CATEGORIES", undecided)

    with pytest.raises(RuntimeError, match="'conditions' has no explicit reference-eligibility decision"):
        build_declaration_index(scenario)


@pytest.mark.parametrize(
    ("field", "ref", "refused_as"),
    [
        ("objective", "agents.blue", None),
        ("objective", "entities.org", None),
        ("objective", "relationships.link", None),
        ("objective", "propositions.ready", None),
        ("objective", "assertions.done", None),
        ("objective", "conditions.alive", "an objective subject"),
        ("objective", "injects.notice", "an objective subject"),
        ("objective", "action_contracts.probe", "an objective subject"),
        ("interaction", "agents.blue", None),
        ("interaction", "entities.org", None),
        ("interaction", "nodes.web.services.http", None),
        ("interaction", "propositions.ready", "an action target"),
        ("interaction", "assertions.done", "an action target"),
        ("interaction", "observation_boundaries.view", "an action target"),
        ("shared-state", "relationships.link", None),
        ("shared-state", "agents.blue", "shared state"),
        ("shared-state", "entities.org", "shared state"),
        ("effect", "agents.blue", None),
        ("effect", "content.private-answer-key", None),
        ("effect", "assertions.done", "an action target"),
        ("authority-scope", "action_contracts.probe", None),
        ("authority-scope", "observation_boundaries.view", None),
        ("authority-scope", "entities.org", None),
        ("authority-scope", "propositions.ready", "an authority scope"),
        ("authority-scope", "conditions.alive", "an authority scope"),
    ],
)
def test_each_reference_purpose_admits_only_its_declaration_kinds(field: str, ref: str, refused_as: str | None) -> None:
    payload = _set(_payload(), FIELDS[field], ref)

    if refused_as is None:
        assert compile_scenario_runtime_model(_parse(payload)) is not None
        return
    with pytest.raises(SDLValidationError) as caught:
        _parse(payload)
    assert any(f"{ref} is not eligible as {refused_as}" in error for error in caught.value.errors)


def test_a_targeted_participant_gains_no_participation_authority_or_visibility() -> None:
    payload = _set(_set(_payload(), FIELDS["interaction"], "agents.blue"), FIELDS["effect"], "agents.blue")
    payload["objectives"]["goal"]["targets"] = ["agents.blue", "entities.org"]

    model = compile_scenario_runtime_model(_parse(payload))

    assert set(model.participant_behaviors) == {"participant.behavior.red", "participant.behavior.blue"}
    blue = model.participant_behaviors["participant.behavior.blue"]
    assert (blue.action_contract_addresses, blue.observation_boundary_addresses) == ((), ())
    assert (blue.authority_anchor_refs, blue.operating_scope_refs) == ((), ())
    red = model.participant_behaviors["participant.behavior.red"]
    assert red.action_contract_addresses == ("participant.action-contract.probe",)
    assert red.authority_anchor_refs == ()
    payload["relationships"]["pair"] = {
        "type": "participant",
        "source": "red",
        "target": "entities.org",
        "participant": {"kind": "cooperation"},
    }
    with pytest.raises(SDLValidationError, match="target participant endpoint must resolve unambiguously"):
        _parse(payload)


def test_bare_names_resolve_among_the_declarations_each_purpose_admits() -> None:
    payload = _payload()
    payload["entities"]["blue"] = {"role": "blue"}
    payload["relationships"]["pair"] = {
        "type": "participant",
        "source": "red",
        "target": "blue",
        "participant": {"kind": "cooperation"},
    }
    _set(payload, FIELDS["interaction"], "blue")
    with pytest.raises(SDLValidationError) as caught:
        _parse(payload)
    assert caught.value.errors == [
        "Relationship 'pair' target participant endpoint must resolve unambiguously to a declared agent",
        "Action contract 'probe' interaction[0] target 'blue' is ambiguous; use one of: agents.blue, entities.blue",
    ]
    payload["relationships"]["pair"]["target"] = "agents.blue"
    _parse(_set(payload, FIELDS["interaction"], "agents.blue"))

    shared = _payload()
    shared["propositions"]["web"] = deepcopy(_PROPOSITION)
    shared["relationships"]["link"]["source"] = "nodes.web"
    _parse(_set(shared, FIELDS["interaction"], "web"))
    ambiguous = _set(shared, FIELDS["objective"], "web")
    with pytest.raises(SDLValidationError, match="target 'web' is ambiguous; use one of: nodes.web, propositions.web"):
        _parse(ambiguous)


def _module_payload() -> dict:
    payload = _payload()
    payload["relationships"]["pair"] = {
        "type": "participant",
        "source": "red",
        "target": "blue",
        "participant": {"kind": "cooperation"},
    }
    payload["action_contracts"]["probe"]["effects"][0]["target_refs"] = ["nodes.web", "content.private-answer-key"]
    exports = {key: list(value) for key, value in payload.items() if isinstance(value, dict)}
    payload["module"] = {"id": "example/eligibility", "version": "1.0.0", "exports": exports}
    return payload


def _compose(tmp_path: Path, module: dict):
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(module))
    root = {
        "name": "two-copies",
        "imports": [{"path": "module.yaml", "namespace": name} for name in ("first", "second")],
    }
    (tmp_path / "root.yaml").write_text(yaml.safe_dump(root))
    return parse_sdl_file(tmp_path / "root.yaml")


def test_duplicate_imports_keep_each_purpose_reference_in_its_namespace(tmp_path: Path) -> None:
    scenario = _compose(tmp_path, _module_payload())
    model = compile_scenario_runtime_model(scenario)

    for namespace in ("first", "second"):
        action = scenario.action_contracts[f"{namespace}.probe"]
        assert action.interactions[0].target == f"nodes.{namespace}.web"
        assert action.interactions[0].shared_state_refs == [f"nodes.{namespace}.web"]
        assert action.effects[0].target_refs == [f"nodes.{namespace}.web", "content.private-answer-key"]
        assert scenario.behavior_specifications[f"{namespace}.red-behavior"].authority_scope_refs == [
            f"nodes.{namespace}.web"
        ]
        pair = scenario.relationships[f"{namespace}.pair"]
        assert (pair.source, pair.target) == (f"{namespace}.red", f"{namespace}.blue")
        assert model.objectives[f"evaluation.objective.{namespace}.goal"].spec["targets"] == [f"nodes.{namespace}.web"]

    refused = _set(_module_payload(), FIELDS["objective"], "conditions.alive")
    with pytest.raises(SDLValidationError) as caught:
        _compose(tmp_path, refused)
    assert [error.split(";")[1].strip() for error in caught.value.errors] == [
        "conditions.first.alive is not eligible as an objective subject",
        "conditions.second.alive is not eligible as an objective subject",
    ]


@pytest.mark.parametrize(
    ("path", "accepted", "refused", "diagnostic"),
    [
        (
            FIELDS["objective"],
            "agents.blue",
            "conditions.alive",
            "conditions.alive is not eligible as an objective subject",
        ),
        (
            FIELDS["interaction"],
            "entities.org",
            "assertions.done",
            "assertions.done is not eligible as an action target",
        ),
        (FIELDS["shared-state"], "relationships.link", "agents.blue", "agents.blue is not eligible as shared state"),
        (
            FIELDS["effect"],
            "nodes.web.services.http",
            "propositions.ready",
            "propositions.ready is not eligible as an action target",
        ),
        (
            FIELDS["authority-scope"],
            "observation_boundaries.view",
            "injects.notice",
            "injects.notice is not eligible as an authority scope",
        ),
        (
            ("relationships", "pair", "target"),
            "agents.blue",
            "entities.org",
            "Relationship 'pair' target participant endpoint must resolve unambiguously to a declared agent",
        ),
    ],
    ids=["objective", "interaction", "shared-state", "effect", "authority-scope", "participant-endpoint"],
)
def test_instantiation_rechecks_each_purpose_after_substitution(
    path: tuple, accepted: str, refused: str, diagnostic: str
) -> None:
    payload = _payload()
    payload["variables"] = {"subject": {"type": "string", "default": accepted}}
    payload["relationships"]["pair"] = {
        "type": "participant",
        "source": "red",
        "target": "blue",
        "participant": {"kind": "cooperation"},
    }
    authored = _parse(_set(payload, path, "${subject}"))

    assert compile_scenario_runtime_model(instantiate_scenario(authored, parameters={"subject": accepted})) is not None
    with pytest.raises(SDLInstantiationError) as caught:
        instantiate_scenario(authored, parameters={"subject": refused})
    assert any(diagnostic in error for error in caught.value.errors)


@pytest.mark.parametrize(("member", "accepted"), [("propositions.ready", True), ("conditions.alive", False)])
def test_objective_target_variation_candidates_follow_the_objective_subject_purpose(member: str, accepted: bool):
    payload = _payload()
    payload["variation_points"] = {
        "subjects": {
            "kind": "subset",
            "target": {"kind": "collection", "owner": "goal", "slot": "objectives.targets"},
            "members": {"candidate": {"reference": member}},
        }
    }
    if accepted:
        assert _parse(payload).variation_points["subjects"].members["candidate"].reference == member
        return
    with pytest.raises(SDLValidationError, match="candidate reference is undefined or has the wrong type"):
        _parse(payload)

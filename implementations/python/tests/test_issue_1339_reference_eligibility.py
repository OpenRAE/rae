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
from raes_processor.compiler import compile_runtime_model, compile_scenario_runtime_model
from test_dsl_142_participant_inject_delivery import BINDING_ADDRESS, _external_direction_yaml

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
_CONDITION = {"command": "true", "interval": 5}
_PAIR = {"type": "participant", "source": "red", "target": "blue", "participant": {"kind": "cooperation"}}

# Reference fields by purpose, as paths into _payload().
FIELDS = {
    "objective": ("objectives", "goal", "targets"),
    "interaction": ("action_contracts", "probe", "interactions", 0, "target"),
    "shared-state": ("action_contracts", "probe", "interactions", 0, "shared_state_refs"),
    "effect": ("action_contracts", "probe", "effects", 0, "target_refs"),
    "authority-scope": ("behavior_specifications", "red-behavior", "authority_scope_refs"),
}
LABELS = {
    "objective": "an objective subject",
    "interaction": "an action target",
    "shared-state": "shared state",
    "effect": "an action target",
    "authority-scope": "an authority scope",
}
_PROBE = "participant.action-contract.probe"
_RED = "participant.behavior.red"
# Where the compiled model carries each reference field of _payload().
_COMPILED = {
    FIELDS["objective"]: lambda model: model.objectives["evaluation.objective.goal"].spec["targets"],
    FIELDS["interaction"]: lambda model: model.action_contracts[_PROBE].spec["interactions"][0]["target"],
    FIELDS["shared-state"]: lambda model: model.action_contracts[_PROBE].spec["interactions"][0]["shared_state_refs"],
    FIELDS["effect"]: lambda model: model.action_contracts[_PROBE].spec["effects"][0]["target_refs"],
    FIELDS["authority-scope"]: lambda model: (
        model.behavior_specifications["participant.behavior-specification.red-behavior"].authority_scope_refs
    ),
    ("relationships", "pair", "target"): lambda model: model.relationship_specs["pair"]["target"],
    ("relationships", "link", "target"): lambda model: model.relationship_specs["link"]["target"],
    ("propositions", "ready", "subjects"): lambda model: model.propositions["evaluation.proposition.ready"].spec[
        "subjects"
    ],
    ("agents", "red", "authority_anchors"): lambda model: model.participant_behaviors[_RED].authority_anchor_refs,
    ("agents", "red", "operating_scope"): lambda model: model.participant_behaviors[_RED].operating_scope_refs,
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
            "conditions": {"alive": _CONDITION},
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


def _refusal(purpose_label: str, ref: str) -> str:
    return f"does not reference any defined element eligible as {purpose_label}; it names {ref}"


def _ambiguous_web(purpose_label: str) -> str:
    """The diagnostic for bare 'web' when node 'web' and condition 'web' are both declared."""

    return f"'web' is ambiguous; use one of: nodes.web; not eligible as {purpose_label}: conditions.web"


def _carried(model, path: tuple) -> list[str]:
    """Return the references that the compiled model keeps for the field at *path*."""

    value = _COMPILED[path](model)
    return [value] if isinstance(value, str) else list(value)


def _with_condition_named_web(payload: dict) -> dict:
    """Share the node's bare name with a declaration that no narrowed purpose admits."""

    payload["conditions"]["web"] = deepcopy(_CONDITION)
    payload["relationships"]["link"]["source"] = "nodes.web"
    return payload


def test_every_indexed_section_and_runtime_family_has_an_explicit_decision() -> None:
    decided = policy.DECLARATION_CATEGORIES.keys() | policy.UNREFERENCEABLE_KINDS
    section_kinds = {policy.section_declaration_kind(section) for section in HASHMAP_SECTIONS}
    payload = _payload()
    payload["nodes"]["web"]["runtime"] = {
        "database_services": [{"database_service_id": "db", "databases": [{"database_id": "app", "name": "app"}]}],
        "dns_services": [
            {
                "dns_service_id": "dns",
                "zones": [
                    {
                        "zone_id": "corp",
                        "name": "corp.example",
                        "rrsets": [
                            {
                                "rrset_id": "www",
                                "owner": "www",
                                "record_type": "A",
                                "records": [{"address": "192.0.2.10"}],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    # A runtime family, a child record, and a nested child record, as the index registers them.
    runtime = {
        declaration.kind: policy.DECLARATION_CATEGORIES[declaration.kind]
        for declaration in build_declaration_index(_parse(payload)).declarations
        if ".runtime." in declaration.address
    }

    assert sorted(section_kinds - decided) == []
    assert not policy.DECLARATION_CATEGORIES.keys() & policy.UNREFERENCEABLE_KINDS
    assert sorted(runtime) == [
        "runtime-database_services",
        "runtime-databases",
        "runtime-dns_services",
        "runtime-rrsets",
        "runtime-zones",
    ]
    assert set(runtime.values()) == {policy.DeclarationCategory.RESOURCE}
    for purpose in policy.ReferencePurpose:
        assert policy.ELIGIBLE_KINDS[purpose] <= policy.ELIGIBLE_KINDS[policy.resolution_domain(purpose)]


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
        ("effect", "content.answer-key", None),
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
    payload["content"] = {"answer-key": {"type": "file", "target": "web", "path": "/opt/key.txt", "text": "key"}}

    if refused_as is None:
        assert _carried(compile_scenario_runtime_model(_parse(payload)), FIELDS[field]) == [ref]
        return
    with pytest.raises(SDLValidationError) as caught:
        _parse(payload)
    assert any(_refusal(refused_as, ref) in error for error in caught.value.errors)


def test_an_effect_ref_that_names_no_declaration_stays_boundary_information() -> None:
    payload = _set(_payload(), FIELDS["effect"], "content.private-answer-key")

    model = compile_scenario_runtime_model(_parse(payload))

    effect = model.action_contracts["participant.action-contract.probe"].spec["effects"][0]
    assert effect["target_refs"] == ["content.private-answer-key"]


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
    payload["relationships"]["pair"] = {**_PAIR, "target": "entities.org"}
    with pytest.raises(SDLValidationError, match="target participant endpoint must resolve unambiguously"):
        _parse(payload)


def test_a_bare_name_shared_by_two_eligible_declarations_needs_the_qualified_form() -> None:
    payload = _payload()
    payload["entities"]["blue"] = {"role": "blue"}
    payload["relationships"]["pair"] = deepcopy(_PAIR)
    _set(payload, FIELDS["interaction"], "blue")
    with pytest.raises(SDLValidationError) as caught:
        _parse(payload)
    assert caught.value.errors == [
        "Relationship 'pair' target participant endpoint must resolve unambiguously to a declared agent",
        "Action contract 'probe' interaction[0] target 'blue' is ambiguous; use one of: agents.blue, entities.blue",
    ]
    payload["relationships"]["pair"]["target"] = "agents.blue"

    model = compile_scenario_runtime_model(_parse(_set(payload, FIELDS["interaction"], "agents.blue")))

    assert (
        model.action_contracts["participant.action-contract.probe"].spec["interactions"][0]["target"] == "agents.blue"
    )


@pytest.mark.parametrize("field", ["objective", "interaction", "shared-state", "effect", "authority-scope"])
def test_a_bare_name_shared_with_an_ineligible_declaration_stays_ambiguous(field: str) -> None:
    """Narrowing only refuses: the bare name resolves where it did before, so it never compiles to nothing."""

    payload = _with_condition_named_web(_payload())
    bare = _set(deepcopy(payload), FIELDS[field], "web")
    with pytest.raises(SDLValidationError) as caught:
        _parse(bare)
    (error,) = caught.value.errors
    assert error.endswith(_ambiguous_web(LABELS[field]))

    model = compile_scenario_runtime_model(_parse(_set(payload, FIELDS[field], "nodes.web")))

    assert _carried(model, FIELDS[field]) == ["nodes.web"]
    behavior = model.behavior_specifications["participant.behavior-specification.red-behavior"]
    assert behavior.authority_scope_addresses == ("provision.node.web",)


def test_bare_mixed_control_and_delivery_scopes_shared_with_a_condition_are_refused() -> None:
    source = (
        _external_direction_yaml()
        .replace("\nentities:\n", '\nconditions:\n  web:\n    command: "true"\n    interval: 5\nentities:\n', 1)
        .replace("scope_refs: [web, entities.blue-team]", "scope_refs: [nodes.web, entities.blue-team]")
    )
    delivery = compile_runtime_model(parse_sdl(source)).participant_inject_deliveries[BINDING_ADDRESS]
    assert delivery.control_authority_scope_addresses == ("provision.node.web",)
    bare = source.replace("          scope_refs: [nodes.web]\n", "          scope_refs: [web]\n").replace(
        "control_authority_scope_refs: [nodes.web]", "control_authority_scope_refs: [web]"
    )

    with pytest.raises(SDLValidationError) as caught:
        parse_sdl(bare)

    refusal = _ambiguous_web("an authority scope")
    assert [error for error in caught.value.errors if error.endswith(refusal)] == [
        f"Behavior specification 'red-briefing' mixed_control controller state '{state}' scope_ref {refusal}"
        for state in ("autonomous", "pending", "directed")
    ]


def _module_payload() -> dict:
    payload = _payload()
    payload["relationships"]["pair"] = deepcopy(_PAIR)
    payload["agents"]["red"].update(authority_anchors=["entities.org"], operating_scope=["web"])
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
        link = scenario.relationships[f"{namespace}.link"]
        assert (link.source, link.target) == (f"{namespace}.web", f"nodes.{namespace}.web.services.http")
        assert scenario.propositions[f"{namespace}.ready"].subjects == [f"nodes.{namespace}.web"]
        red = model.participant_behaviors[f"participant.behavior.{namespace}.red"]
        assert red.authority_anchor_refs == (f"entities.{namespace}.org",)
        assert red.operating_scope_addresses == (f"provision.node.{namespace}.web",)
        assert model.objectives[f"evaluation.objective.{namespace}.goal"].spec["targets"] == [f"nodes.{namespace}.web"]

    refused = _set(_module_payload(), FIELDS["objective"], "conditions.alive")
    with pytest.raises(SDLValidationError) as caught:
        _compose(tmp_path, refused)
    assert [error.split(" target ", 1)[1] for error in caught.value.errors] == [
        f"'conditions.{namespace}.alive' {_refusal('an objective subject', f'conditions.{namespace}.alive')}"
        for namespace in ("first", "second")
    ]


@pytest.mark.parametrize(
    ("path", "accepted", "refused", "diagnostic"),
    [
        (FIELDS["objective"], "agents.blue", "conditions.alive", _refusal("an objective subject", "conditions.alive")),
        (FIELDS["interaction"], "entities.org", "assertions.done", _refusal("an action target", "assertions.done")),
        (FIELDS["shared-state"], "relationships.link", "agents.blue", _refusal("shared state", "agents.blue")),
        (
            FIELDS["effect"],
            "nodes.web.services.http",
            "propositions.ready",
            _refusal("an action target", "propositions.ready"),
        ),
        (
            FIELDS["authority-scope"],
            "observation_boundaries.view",
            "injects.notice",
            _refusal("an authority scope", "injects.notice"),
        ),
        (
            ("relationships", "pair", "target"),
            "agents.blue",
            "entities.org",
            "Relationship 'pair' target participant endpoint must resolve unambiguously to a declared agent",
        ),
        (
            ("relationships", "link", "target"),
            "entities.org",
            "objectives.goal",
            "target 'objectives.goal' does not reference any defined targetable element; it names objectives.goal",
        ),
        (
            ("propositions", "ready", "subjects"),
            "agents.blue",
            "objectives.goal",
            "subject 'objectives.goal' does not reference any defined targetable element; it names objectives.goal",
        ),
        (
            ("agents", "red", "authority_anchors"),
            "entities.org",
            "scenario.reference-eligibility",
            "authority_anchor 'scenario.reference-eligibility' does not reference any defined element",
        ),
        (
            ("agents", "red", "operating_scope"),
            "web",
            "relationships.link",
            "operating_scope 'relationships.link' does not reference any defined targetable element",
        ),
    ],
    ids=[
        "objective",
        "interaction",
        "shared-state",
        "effect",
        "authority-scope",
        "participant-endpoint",
        "relationship-endpoint",
        "observation-subject",
        "authority-anchor",
        "operating-scope",
    ],
)
def test_instantiation_rechecks_each_purpose_after_substitution(
    path: tuple, accepted: str, refused: str, diagnostic: str
) -> None:
    payload = _payload()
    payload["variables"] = {"subject": {"type": "string", "default": accepted}}
    payload["relationships"]["pair"] = deepcopy(_PAIR)
    payload["agents"]["red"].update(authority_anchors=[], operating_scope=[])
    authored = _parse(_set(payload, path, "${subject}"))

    model = compile_scenario_runtime_model(instantiate_scenario(authored, parameters={"subject": accepted}))
    assert _carried(model, path) == [accepted]
    with pytest.raises(SDLInstantiationError) as caught:
        instantiate_scenario(authored, parameters={"subject": refused})
    assert any(diagnostic in error for error in caught.value.errors)


@pytest.mark.parametrize(
    ("member", "accepted"),
    [("propositions.ready", True), ("nodes.web", True), ("conditions.alive", False), ("web", False)],
)
def test_objective_target_variation_candidates_follow_the_objective_subject_purpose(member: str, accepted: bool):
    payload = _with_condition_named_web(_payload())
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

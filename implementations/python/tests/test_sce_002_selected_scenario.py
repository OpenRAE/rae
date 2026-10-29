"""SDL-owned selected-scenario admission tests for SCE-002."""

from __future__ import annotations

import json

import pytest
from raes import (
    ExpandedScenarioBindingTargetResolver,
    admit_scenario_family,
    parse_sdl,
    select_scenario_family,
)
from raes.scenario import ExpandedScenario, Scenario
from raes.selected_scenario import SDLSelectionError
from raes.validator import SemanticValidator
from raes_contracts.contracts import (
    ExperimentSelectionMemberOutcomeModel,
    ExperimentSelectionOrderOutcomeModel,
    ExperimentSelectionReferenceOutcomeModel,
    ExperimentSelectionSubsetOutcomeModel,
    LiteralBindingValueModel,
)


def _family() -> ExpandedScenario:
    payload: dict[str, object] = {
        "name": "compiler-family",
        "variables": {
            "payload_path": {
                "type": "string",
                "default": "/opt/a",
                "allowed_values": ["/opt/a", "/opt/b"],
            }
        },
        "nodes": {
            "primary": {
                "type": "compute",
                "os": "linux",
                "resources": {"ram": "1 gib", "cpu": 1},
            },
            "secondary": {
                "type": "compute",
                "os": "linux",
                "resources": {"ram": "1 gib", "cpu": 1},
            },
        },
        "content": {
            "payload": {
                "type": "file",
                "target": "primary",
                "path": "${payload_path}",
            }
        },
        "variation_points": {
            "payload-path": {
                "kind": "parameter",
                "target": {"kind": "variable", "variable": "payload_path"},
                "domain": {"kind": "enum", "values": ["/opt/b", "/opt/a"]},
            },
            "payload-host": {
                "kind": "alternative",
                "target": {"kind": "reference", "owner": "payload", "slot": "content.target"},
                "alternatives": {
                    "primary-host": {"reference": "primary"},
                    "secondary-host": {"reference": "secondary"},
                },
            },
        },
    }
    return admit_scenario_family(parse_sdl(json.dumps(payload)))


def _all_kinds_family() -> ExpandedScenario:
    payload: dict[str, object] = {
        "name": "all-kinds-family",
        "variables": {
            "payload_path": {
                "type": "string",
                "default": "/opt/a",
                "allowed_values": ["/opt/a", "/opt/b"],
            }
        },
        "nodes": {
            "primary": {
                "type": "compute",
                "os": "linux",
                "resources": {"ram": "1 gib", "cpu": 1},
                "features": {"baseline": ""},
            },
            "secondary": {
                "type": "compute",
                "os": "linux",
                "resources": {"ram": "1 gib", "cpu": 1},
            },
        },
        "features": {
            "baseline": {"type": "configuration"},
            "hardened": {"type": "configuration"},
        },
        "content": {
            "payload": {
                "type": "file",
                "target": "primary",
                "path": "${payload_path}",
            }
        },
        "events": {"recon": {}, "exploit": {}},
        "scripts": {
            "recon": {"start_time": 0, "end_time": 10, "speed": 1, "events": {"recon": 0}},
            "exploit": {"start_time": 10, "end_time": 20, "speed": 1, "events": {"exploit": 10}},
        },
        "stories": {"attack": {"scripts": ["recon", "exploit"]}},
        "variation_points": {
            "payload-path": {
                "kind": "parameter",
                "target": {"kind": "variable", "variable": "payload_path"},
                "domain": {"kind": "enum", "values": ["/opt/a", "/opt/b"]},
            },
            "target-ref": {
                "kind": "governed-reference",
                "target": {"kind": "reference", "owner": "payload", "slot": "content.target"},
                "domain": {
                    "kind": "governed-reference",
                    "authority": "inventory-v1",
                    "allowed_refs": ["primary", "secondary"],
                },
            },
            "host-choice": {
                "kind": "alternative",
                "target": {"kind": "reference", "owner": "payload", "slot": "content.target"},
                "alternatives": {
                    "primary-host": {"reference": "primary"},
                    "secondary-host": {"reference": "secondary"},
                },
            },
            "feature-set": {
                "kind": "subset",
                "target": {"kind": "collection", "owner": "primary", "slot": "nodes.features"},
                "members": {
                    "base": {"reference": "baseline"},
                    "extra": {"reference": "hardened"},
                },
                "minimum": 1,
                "maximum": 2,
            },
            "attack-order": {
                "kind": "order",
                "target": {"kind": "collection", "owner": "attack", "slot": "stories.scripts"},
                "members": {
                    "recon-phase": {"reference": "recon"},
                    "exploit-phase": {"reference": "exploit"},
                },
                "precedence": [{"before": "recon-phase", "after": "exploit-phase"}],
            },
            "start-offset": {
                "kind": "logical-timing",
                "target": {"kind": "logical-timing", "owner": "recon", "slot": "scripts.start_time"},
                "domain": {
                    "kind": "numeric-interval",
                    "numeric_type": "integer",
                    "lower": 0,
                    "upper": 5,
                },
                "unit": "seconds",
            },
        },
    }
    authored = Scenario.model_validate(payload)
    SemanticValidator(authored).validate()
    expanded = ExpandedScenario.model_validate(payload)
    expanded._set_semantic_validated(True)
    return expanded


def _all_kinds_outcomes() -> dict[str, object]:
    return {
        "payload-path": LiteralBindingValueModel(kind="literal", value="/opt/b"),
        "target-ref": ExperimentSelectionReferenceOutcomeModel(
            kind="reference",
            reference_id="secondary",
        ),
        "host-choice": ExperimentSelectionMemberOutcomeModel(
            kind="member",
            member_id="secondary-host",
        ),
        "feature-set": ExperimentSelectionSubsetOutcomeModel(
            kind="subset",
            member_ids=["base", "extra"],
        ),
        "attack-order": ExperimentSelectionOrderOutcomeModel(
            kind="order",
            member_ids=["recon-phase", "exploit-phase"],
        ),
        "start-offset": LiteralBindingValueModel(kind="literal", value=0),
    }


def test_complete_selection_constructs_and_semantically_admits_concrete_scenario() -> None:
    selected = select_scenario_family(
        _family(),
        {
            "payload-path": LiteralBindingValueModel(kind="literal", value="/opt/b"),
            "payload-host": ExperimentSelectionMemberOutcomeModel(kind="member", member_id="secondary-host"),
        },
    )

    assert selected.semantic_validated
    assert not hasattr(selected, "variation_points")
    assert selected.content["payload"].target == "secondary"
    assert selected.instantiation_provenance.bindings[0].value == "/opt/b"


def test_incomplete_selection_fails_closed_without_disclosing_values() -> None:
    family = _family()
    outcomes = {"payload-path": LiteralBindingValueModel(kind="literal", value="/opt/b")}

    with pytest.raises(SDLSelectionError) as raised:
        select_scenario_family(family, outcomes)

    assert "payload-host" in str(raised.value)
    assert "/opt/b" not in str(raised.value)


def test_scenario_binding_resolver_returns_canonical_typed_target() -> None:
    resolution = ExpandedScenarioBindingTargetResolver(_family()).resolve(
        "compiler-family",
        "payload-path",
        "variables.payload_path",
    )

    assert resolution.canonical_target_id == "variables.payload_path"
    assert resolution.value_type == "string"
    assert resolution.allowed_value_kinds == ["literal"]


def test_every_variation_target_kind_is_applied_before_whole_scenario_admission() -> None:
    selected = select_scenario_family(_all_kinds_family(), _all_kinds_outcomes())

    assert selected.content["payload"].target == "secondary"
    assert set(selected.nodes["primary"].features) == {"baseline", "hardened"}
    assert selected.stories["attack"].scripts == ["recon", "exploit"]
    assert selected.scripts["recon"].start_time == 0
    assert selected.instantiation_provenance.bindings[0].value == "/opt/b"


def test_conflicting_writers_to_one_canonical_target_fail_before_application() -> None:
    outcomes = _all_kinds_outcomes()
    outcomes["target-ref"] = ExperimentSelectionReferenceOutcomeModel(
        kind="reference",
        reference_id="primary",
    )
    family = _all_kinds_family()

    with pytest.raises(SDLSelectionError, match="conflicting values"):
        select_scenario_family(family, outcomes)


def test_cross_point_requires_constraint_is_enforced_before_application() -> None:
    family = _all_kinds_family()
    payload = family.model_dump(mode="python", by_alias=True)
    payload["variation_points"]["host-choice"]["alternatives"]["secondary-host"]["requires"] = [
        {"point": "feature-set", "members": ["extra"]}
    ]
    constrained = ExpandedScenario.model_validate(payload)
    SemanticValidator(constrained).validate()
    constrained._set_semantic_validated(True)
    outcomes = _all_kinds_outcomes()
    outcomes["feature-set"] = ExperimentSelectionSubsetOutcomeModel(kind="subset", member_ids=["base"])

    with pytest.raises(SDLSelectionError, match="violates requires"):
        select_scenario_family(constrained, outcomes)


def test_post_selection_whole_scenario_semantics_reject_invalid_timing() -> None:
    outcomes = _all_kinds_outcomes()
    outcomes["start-offset"] = LiteralBindingValueModel(kind="literal", value=5)
    family = _all_kinds_family()

    with pytest.raises(SDLSelectionError, match="whole-scenario semantic admission") as raised:
        select_scenario_family(family, outcomes)

    assert "input_value" not in str(raised.value)

"""SCE-002 bounded SDL scenario-family variation points."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import SDLInstantiationError, SDLParseError, SDLValidationError
from raes._declarations import build_declaration_index
from raes.canonical import canonical_sdl_bytes, canonical_sdl_digest
from raes.instantiate import instantiate_scenario
from raes.language_service import language_completions, language_references
from raes.parser import parse_sdl_file
from raes.scenario import InstantiatedScenario, Scenario
from raes.validator import SemanticValidator
from raes_contracts.bounded_domains import EnumDomain
from raes_contracts.contracts import schema_bundle
from raes_contracts.realization_envelope import EnumDomain as EnvelopeEnumDomain

FIXTURE_DIR = Path(__file__).parents[3] / "contracts" / "fixtures" / "sdl" / "variation-points-v1"


def _family_payload() -> dict[str, object]:
    return {
        "name": "bounded-family",
        "variables": {
            "payload_path": {
                "type": "string",
                "default": "/opt/payload-a",
                "allowed_values": ["/opt/payload-a", "/opt/payload-b"],
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
                "domain": {"kind": "enum", "values": ["/opt/payload-a", "/opt/payload-b"]},
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


def _validated_family() -> Scenario:
    scenario = Scenario.model_validate(_family_payload())
    SemanticValidator(scenario).validate()
    scenario._set_semantic_validated(True)
    return scenario


def _write_parameter_family_files(tmp_path: Path, *, bind_owned_variable: bool = False) -> Path:
    module = tmp_path / "parameter-family.yaml"
    module.write_text(
        """
name: parameter-family
version: 1.0.0
module:
  id: acme/parameter-family
  version: 1.0.0
  parameters: [path]
  exports:
    nodes: [host]
    content: [payload]
    variation_points: [payload-path]
variables:
  path: {type: string, required: true, allowed_values: [/opt/a, /opt/b]}
nodes:
  host: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
content:
  payload: {type: file, target: host, path: '${path}'}
variation_points:
  payload-path:
    kind: parameter
    target: {kind: variable, variable: path}
    domain: {kind: enum, values: [/opt/a, /opt/b]}
""".lstrip(),
        encoding="utf-8",
    )
    parameter_binding = "\n    parameters: {path: /opt/a}" if bind_owned_variable else ""
    root = tmp_path / "root.yaml"
    root.write_text(
        f"""
name: root
imports:
  - path: parameter-family.yaml
    namespace: shared
    version: 1.0.0{parameter_binding}
""".lstrip(),
        encoding="utf-8",
    )
    return root


def test_all_six_closed_variation_kinds_are_semantically_admitted() -> None:
    scenario = _validated_family()

    assert {point.kind for point in scenario.variation_points.values()} == {
        "parameter",
        "governed-reference",
        "alternative",
        "subset",
        "order",
        "logical-timing",
    }
    assert isinstance(scenario.variation_points["payload-path"].domain, EnumDomain)
    assert EnvelopeEnumDomain is EnumDomain


def test_variation_registry_is_authoring_only_and_instantiation_fails_closed() -> None:
    scenario = _validated_family()

    with pytest.raises(SDLInstantiationError, match="unresolved variation points"):
        instantiate_scenario(scenario)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InstantiatedScenario.model_validate(
            {
                "name": "invalid-concrete-family",
                "variation_points": {},
                "instantiation_provenance": {
                    "authored_digest": {
                        "profile": "raes-sdl-semantic/v2",
                        "algorithm": "sha256",
                        "value": "sha256:" + "a" * 64,
                    }
                },
            }
        )

    bundle = schema_bundle()
    assert "variation_points" in bundle["sdl-authoring-input-v1"]["properties"]
    assert "variation_points" not in bundle["instantiated-scenario-v1"]["properties"]
    Draft202012Validator.check_schema(bundle["sdl-authoring-input-v1"])


def test_empty_registry_preserves_static_canonical_bytes_and_nonempty_family_changes_identity() -> None:
    implicit = Scenario(name="static")
    explicit = Scenario.model_validate({"name": "static", "variation_points": {}})
    for scenario in (implicit, explicit):
        SemanticValidator(scenario).validate()
        scenario._set_semantic_validated(True)

    assert canonical_sdl_bytes(implicit) == canonical_sdl_bytes(explicit)

    family = _validated_family()
    changed_payload = _family_payload()
    changed_payload["variation_points"]["payload-path"]["domain"] = {
        "kind": "exact",
        "value": "/opt/payload-a",
    }
    changed = Scenario.model_validate(changed_payload)
    SemanticValidator(changed).validate()
    changed._set_semantic_validated(True)
    assert canonical_sdl_digest(family) != canonical_sdl_digest(changed)
    assert "variation_points" in json.loads(canonical_sdl_bytes(family))["scenario"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["variation_points"]["payload-path"].update(
                {"domain": {"kind": "enum", "values": [1, 2]}}
            ),
            "does not match variable type",
        ),
        (
            lambda payload: payload["variation_points"]["host-choice"]["target"].update({"owner": "missing-owner"}),
            "target owner is undefined",
        ),
        (
            lambda payload: payload["variation_points"]["host-choice"]["alternatives"]["primary-host"].update(
                {"requires": [{"point": "missing-point", "members": ["ghost"]}]}
            ),
            "relation point is undefined",
        ),
        (
            lambda payload: payload["variation_points"]["start-offset"].update({"unit": "multiplier"}),
            "unit does not match target",
        ),
    ],
)
def test_semantic_validation_rejects_invalid_domains_targets_relations_and_timing(
    mutate: object,
    message: str,
) -> None:
    payload = deepcopy(_family_payload())
    mutate(payload)
    scenario = Scenario.model_validate(payload)
    validator = SemanticValidator(scenario)

    with pytest.raises(SDLValidationError, match=message):
        validator.validate()


def test_each_declared_candidate_must_pass_the_owning_slot_semantics() -> None:
    payload = _family_payload()
    payload["nodes"]["network"] = {"type": "switch"}
    payload["variation_points"]["host-choice"]["alternatives"]["network"] = {"reference": "network"}
    scenario = Scenario.model_validate(payload)
    validator = SemanticValidator(scenario)

    with pytest.raises(SDLValidationError, match="candidate is invalid for target slot"):
        validator.validate()


def test_each_collection_member_must_pass_the_owning_slot_semantics() -> None:
    payload = deepcopy(_family_payload())
    payload["entities"] = {"blue": {"role": "blue"}}
    payload["propositions"] = {
        "blue-present": {
            "description": "The blue entity is present for objective dependency validation.",
            "subjects": ["entities.blue"],
            "basis": "declared_state",
            "predicate": {
                "kind": "presence",
                "property": "role",
                "semantic_ref": "urn:raes:declared-property:entity-role",
                "operator": "exists",
            },
        }
    }
    payload["assertions"] = {"blue-present": {"proposition": "blue-present", "role": "postcondition"}}
    payload["objectives"] = {
        "self-dependent": {
            "entity": "blue",
            "success": {"assertions": ["blue-present"]},
        }
    }
    payload["variation_points"]["objective-dependencies"] = {
        "kind": "subset",
        "target": {
            "kind": "collection",
            "owner": "self-dependent",
            "slot": "objectives.depends_on",
        },
        "members": {"self": {"reference": "self-dependent"}},
    }
    scenario = Scenario.model_validate(payload)
    validator = SemanticValidator(scenario)

    with pytest.raises(SDLValidationError, match="candidate is invalid for target slot"):
        validator.validate()


def test_domain_constraint_failure_does_not_echo_candidate_values() -> None:
    marker = "credential-material-marker-786"
    payload = deepcopy(_family_payload())
    payload["variation_points"]["payload-path"]["domain"] = {
        "kind": "enum",
        "values": [marker],
    }
    scenario = Scenario.model_validate(payload)
    validator = SemanticValidator(scenario)

    with pytest.raises(SDLValidationError) as caught:
        validator.validate()
    assert marker not in str(caught.value)


def test_structural_constraints_reject_empty_subset_bounds_and_order_cycles() -> None:
    subset = deepcopy(_family_payload())
    subset["variation_points"]["feature-set"].update({"minimum": 2, "maximum": 1})
    with pytest.raises(ValidationError, match="minimum must not exceed maximum"):
        Scenario.model_validate(subset)

    order = deepcopy(_family_payload())
    order["variation_points"]["attack-order"]["precedence"].append({"before": "exploit-phase", "after": "recon-phase"})
    with pytest.raises(ValidationError, match="precedence graph must be acyclic"):
        Scenario.model_validate(order)

    impossible_order = deepcopy(_family_payload())
    impossible_order["variation_points"]["attack-order"]["fixed_positions"] = {
        "recon-phase": 1,
        "exploit-phase": 0,
    }
    with pytest.raises(ValidationError, match="admit at least one ordering"):
        Scenario.model_validate(impossible_order)


def test_integer_interval_must_contain_an_integer_member() -> None:
    payload = deepcopy(_family_payload())
    payload["variation_points"]["start-offset"]["domain"] = {
        "kind": "numeric-interval",
        "numeric_type": "integer",
        "lower": 0,
        "upper": 1,
        "lower_closed": False,
        "upper_closed": False,
    }

    scenario = Scenario.model_validate(payload)
    validator = SemanticValidator(scenario)
    with pytest.raises(SDLValidationError, match="domain is empty"):
        validator.validate()


def test_cross_point_constraints_must_have_a_satisfying_selection() -> None:
    payload = deepcopy(_family_payload())
    payload["content"]["payload-copy"] = {
        "type": "file",
        "target": "primary",
        "path": "/opt/copy",
    }
    payload["variation_points"]["second-host-choice"] = {
        "kind": "alternative",
        "target": {"kind": "reference", "owner": "payload-copy", "slot": "content.target"},
        "alternatives": {
            "first": {"reference": "primary"},
            "second": {"reference": "secondary"},
        },
    }
    exclusion = [{"point": "second-host-choice", "members": ["first", "second"]}]
    payload["variation_points"]["host-choice"]["alternatives"]["primary-host"]["excludes"] = exclusion
    payload["variation_points"]["host-choice"]["alternatives"]["secondary-host"]["excludes"] = exclusion

    scenario = Scenario.model_validate(payload)
    validator = SemanticValidator(scenario)
    with pytest.raises(SDLValidationError, match="no satisfying selection"):
        validator.validate()


def test_every_structural_member_must_participate_in_a_satisfying_selection() -> None:
    payload = deepcopy(_family_payload())
    payload["content"]["payload-copy"] = {
        "type": "file",
        "target": "primary",
        "path": "/opt/copy",
    }
    payload["variation_points"]["second-host-choice"] = {
        "kind": "alternative",
        "target": {"kind": "reference", "owner": "payload-copy", "slot": "content.target"},
        "alternatives": {
            "first": {"reference": "primary"},
            "second": {"reference": "secondary"},
        },
    }
    payload["variation_points"]["host-choice"]["alternatives"]["primary-host"]["excludes"] = [
        {"point": "second-host-choice", "members": ["first", "second"]}
    ]

    scenario = Scenario.model_validate(payload)
    validator = SemanticValidator(scenario)
    with pytest.raises(SDLValidationError, match="member 'primary-host' cannot participate"):
        validator.validate()


@pytest.mark.parametrize(
    ("point_name", "first_member", "second_member"),
    [
        ("feature-set", "base", "extra"),
        ("attack-order", "recon-phase", "exploit-phase"),
    ],
)
def test_subset_cardinality_and_order_members_participate_in_family_satisfiability(
    point_name: str,
    first_member: str,
    second_member: str,
) -> None:
    payload = deepcopy(_family_payload())
    point = payload["variation_points"][point_name]
    if point_name == "feature-set":
        point["minimum"] = 2
    point["members"][first_member]["requires"] = [{"point": "host-choice", "members": ["primary-host"]}]
    point["members"][second_member]["excludes"] = [{"point": "host-choice", "members": ["primary-host"]}]

    scenario = Scenario.model_validate(payload)
    validator = SemanticValidator(scenario)
    with pytest.raises(SDLValidationError, match="no satisfying selection"):
        validator.validate()


def test_module_composition_namespaces_exported_and_private_points_and_nested_references(tmp_path) -> None:
    module = tmp_path / "family.yaml"
    module.write_text(
        """
name: family
version: 1.0.0
module:
  id: acme/family
  version: 1.0.0
  exports:
    nodes: [primary, secondary]
    content: [payload]
    variation_points: [host-choice]
nodes:
  primary: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
  secondary: {type: compute, os: linux, resources: {ram: 1 gib, cpu: 1}}
content:
  payload: {type: file, target: primary, path: /opt/payload}
variation_points:
  private-choice:
    kind: alternative
    target: {kind: reference, owner: payload, slot: content.target}
    alternatives:
      private-primary: {reference: primary}
      private-secondary: {reference: secondary}
  host-choice:
    kind: alternative
    target: {kind: reference, owner: payload, slot: content.target}
    alternatives:
      primary-host:
        reference: primary
        requires: [{point: private-choice, members: [private-primary]}]
      secondary-host: {reference: secondary}
""".lstrip(),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        """
name: root
imports:
  - path: family.yaml
    namespace: shared
    version: 1.0.0
""".lstrip(),
        encoding="utf-8",
    )

    expanded = parse_sdl_file(root)
    assert set(expanded.variation_points) == {
        "shared.host-choice",
        "shared.__private.private-choice",
    }
    point = expanded.variation_points["shared.host-choice"]
    assert point.target.owner == "shared.payload"
    assert point.alternatives["primary-host"].reference == "shared.primary"
    assert point.alternatives["primary-host"].requires[0].point == "shared.__private.private-choice"

    declarations = build_declaration_index(expanded)
    assert "variation_points.shared.host-choice" in declarations.addresses
    assert "variation_points.shared.host-choice.alternatives.primary-host" in declarations.addresses


def test_imported_parameter_point_preserves_and_namespaces_its_variable_target(tmp_path) -> None:
    root = _write_parameter_family_files(tmp_path)

    expanded = parse_sdl_file(root)
    qualified_variable = "shared.__private.path"
    assert set(expanded.variables) == {qualified_variable}
    assert expanded.content["shared.payload"].path == "${shared.__private.path}"
    assert expanded.variation_points["shared.payload-path"].target.variable == qualified_variable


def test_import_cannot_bind_a_variable_owned_by_a_parameter_point(tmp_path) -> None:
    root = _write_parameter_family_files(tmp_path, bind_owned_variable=True)

    with pytest.raises(
        SDLParseError,
        match="owned by a variation point and cannot be bound during composition",
    ):
        parse_sdl_file(root)


def test_language_service_exposes_variation_fields_targets_and_nested_definitions() -> None:
    source = """\
name: family
variables:
  path: {type: string, default: /opt/a}
nodes:
  primary: {type: compute, resources: {ram: 1 GiB, cpu: 1}}
  secondary: {type: compute, resources: {ram: 1 GiB, cpu: 1}}
content:
  payload: {type: file, target: primary, path: '${path}'}
variation_points:
  host-choice:
    kind: alternative
    target: {kind: reference, owner: payload, slot: content.target}
    alternatives:
      primary-host: {reference: primary}
      secondary-host:
        reference: secondary
        requires: [{point: host-choice, members: [primary-host]}]
"""

    fields = language_completions(source, cursor_path="/variation_points/host-choice")
    assert {"kind", "target", "alternatives", "domain"}.issubset({item["label"] for item in fields["items"]})
    assert {
        item["label"]
        for item in language_completions(
            source,
            cursor_path="/variation_points/host-choice/target/owner",
        )["items"]
    } >= {"payload", "primary"}
    assert {
        item["label"]
        for item in language_completions(
            source,
            cursor_path="/variation_points/host-choice/alternatives/secondary-host/requires/0/point",
        )["items"]
    } == {"host-choice"}

    references = language_references(
        source,
        "variation_points.host-choice.alternatives.primary-host",
    )
    assert [item["path"] for item in references["definitions"]] == [
        "/variation_points/host-choice/alternatives/primary-host"
    ]
    assert any(item["path"].endswith("/requires/0/members/0") for item in references["occurrences"])


def test_variation_fixture_corpus_covers_valid_invalid_composed_and_canonical_forms() -> None:
    admitted = parse_sdl_file(FIXTURE_DIR / "valid" / "family.yaml")
    assert set(admitted.variation_points) == {"payload-path", "payload-host"}

    with pytest.raises(SDLValidationError):
        parse_sdl_file(FIXTURE_DIR / "invalid" / "dangling-candidate.yaml")

    composed = parse_sdl_file(FIXTURE_DIR / "composition" / "root.yaml")
    assert set(composed.variation_points) == {
        "shared.payload-host",
        "shared.__private.private-host",
    }
    assert (
        composed.variation_points["shared.payload-host"].alternatives["primary-host"].requires[0].point
        == "shared.__private.private-host"
    )

    absent = parse_sdl_file(FIXTURE_DIR / "canonical" / "absent.yaml")
    empty = parse_sdl_file(FIXTURE_DIR / "canonical" / "empty.yaml")
    assert canonical_sdl_bytes(absent) == canonical_sdl_bytes(empty)

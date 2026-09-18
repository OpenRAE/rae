"""Regression coverage for extensible HTTP wire-method identity (issue #1298)."""

from __future__ import annotations

import json
import textwrap
from copy import deepcopy

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import SDLInstantiationError, SDLParseError, instantiate_scenario, parse_sdl, parse_sdl_file
from raes.canonical import InstantiatedScenarioSnapshot, canonical_instantiated_sdl_bytes
from raes.runtime_application import RuntimeApplicationRoute, RuntimeApplicationSurface
from raes_contracts.contracts import schema_bundle
from raes_processor.compiler import compile_runtime_model
from test_issue_1210_semantic_comparison import compare


def _source(*methods: str, variable: bool = False) -> str:
    method_values = ["${route_method}"] if variable else list(methods)
    payload: dict[str, object] = {
        "name": "http-method-identity",
        "realization": {"default": "open"},
        "nodes": {
            "host": {
                "type": "compute",
                "services": [{"name": "web", "port": 8080}],
                "runtime": {
                    "applications": [
                        {
                            "application_id": "documents",
                            "service": "web",
                            "protocol": "http",
                            "routes": [
                                {
                                    "route_id": "documents",
                                    "path": "/documents",
                                    "methods": method_values,
                                }
                            ],
                        }
                    ]
                },
            }
        },
    }
    if variable:
        payload["variables"] = {"route_method": {"type": "string", "default": "PROPFIND"}}
    return yaml.safe_dump(payload, sort_keys=False)


def _methods(scenario, node: str = "host") -> list[str]:
    return scenario.nodes[node].runtime.applications[0].routes[0].methods


@pytest.mark.parametrize("method", ["PROPFIND", "PrivateQuery", "privateQuery", "M-SEARCH", "X!#$%&'*+.^_`|~"])
def test_valid_extension_method_identity_is_preserved(method: str) -> None:
    route = RuntimeApplicationRoute(route_id="documents", path="/documents", methods=[method])
    assert route.methods == [method]


@pytest.mark.parametrize("method", ["get", "Get", "GET", "patch", "PaTcH"])
def test_legacy_builtin_spellings_keep_their_uppercase_compatibility_identity(method: str) -> None:
    route = RuntimeApplicationRoute(route_id="documents", path="/documents", methods=[method])
    assert route.methods == [method.upper()]


@pytest.mark.parametrize(
    "method",
    ["", " FETCH", "FETCH ", "FET CH", "FETCH/ITEM", "FETCH\n", "méthod", "x" * 129],
)
def test_invalid_method_tokens_are_rejected_without_repair(method: str) -> None:
    with pytest.raises(ValidationError, match="HTTP method"):
        RuntimeApplicationRoute(route_id="documents", path="/documents", methods=[method])


def test_parser_diagnostic_does_not_echo_a_rejected_method() -> None:
    rejected = "PRIVATE INVALID METHOD 1298"
    with pytest.raises(SDLParseError) as caught:
        parse_sdl(_source(rejected))
    assert rejected not in str(caught.value)


def test_duplicates_use_post_compatibility_identity_but_extension_case_remains_distinct() -> None:
    for methods in (["PROPFIND", "PROPFIND"], ["get", "GET"]):
        with pytest.raises(ValidationError, match="unique after compatibility normalization"):
            RuntimeApplicationRoute(route_id="duplicate", path="/documents", methods=methods)

    with pytest.raises(ValidationError, match="Duplicate runtime application route binding"):
        RuntimeApplicationSurface(
            application_id="documents",
            routes=[
                {"route_id": "lower", "path": "/documents", "methods": ["get"]},
                {"route_id": "upper", "path": "/documents", "methods": ["GET"]},
            ],
        )
    surface = RuntimeApplicationSurface(
        application_id="documents",
        routes=[
            {"route_id": "first", "path": "/documents", "methods": ["PROPFIND"]},
            {"route_id": "second", "path": "/documents", "methods": ["PropFind"]},
        ],
    )
    assert [route.methods for route in surface.routes] == [["PROPFIND"], ["PropFind"]]


def test_variable_substitution_is_revalidated_as_a_method_token() -> None:
    authored = parse_sdl(_source(variable=True))
    assert _methods(instantiate_scenario(authored)) == ["PROPFIND"]
    assert _methods(instantiate_scenario(authored, parameters={"route_method": "PrivateQuery"})) == ["PrivateQuery"]
    with pytest.raises(SDLInstantiationError) as caught:
        instantiate_scenario(authored, parameters={"route_method": "PRIVATE INVALID METHOD 1298"})
    assert "value_error" in str(caught.value)
    assert "PRIVATE INVALID METHOD 1298" not in str(caught.value)


def test_composition_compile_comparison_and_snapshot_preserve_exact_identity(tmp_path) -> None:
    module = yaml.safe_load(_source("PROPFIND", "PrivateQuery", "privateQuery"))
    module["module"] = {"id": "example/http-methods", "version": "1.0.0", "exports": {"nodes": ["host"]}}
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(module, sort_keys=False))
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: composed-http-methods
            realization: {default: open}
            imports: [{path: module.yaml, namespace: component}]
            """
        )
    )
    expanded = parse_sdl_file(root)
    assert expanded.nodes["component.host"].runtime.applications[0].routes[0].methods == [
        "PROPFIND",
        "PrivateQuery",
        "privateQuery",
    ]
    instantiated = instantiate_scenario(expanded)
    compiled = compile_runtime_model(instantiated)
    requirement = next(
        item for item in compiled.realization_requirements if item.requirement_kind == "runtime-applications"
    )
    route_constraints = requirement.constraint_document.root.items[0].fields["routes"].items[0].fields
    assert [item.value for item in route_constraints["methods"].items] == [
        "PROPFIND",
        "PrivateQuery",
        "privateQuery",
    ]
    assert compiled.observation_demands == ()
    assert compiled.action_contracts == {}

    encoded = canonical_instantiated_sdl_bytes(instantiated)
    restored = InstantiatedScenarioSnapshot.model_validate_json(encoded).scenario
    assert canonical_instantiated_sdl_bytes(restored) == encoded
    assert _methods(restored, "component.host") == ["PROPFIND", "PrivateQuery", "privateQuery"]

    case_changed = parse_sdl(_source("PROPFIND", "PrivateQuery", "Privatequery"))
    assert (
        compare(parse_sdl(_source("PROPFIND", "PrivateQuery", "privateQuery")), case_changed)
        .changes[0]
        .semantic_relation.value
        == "changed"
    )


def test_authoring_schema_matches_model_token_and_collection_rules() -> None:
    schema = schema_bundle()["sdl-authoring-input-v1"]
    validator = Draft202012Validator(schema)
    valid = yaml.safe_load(_source("PROPFIND", "PrivateQuery", "privateQuery"))
    assert validator.is_valid(valid)
    variable = yaml.safe_load(_source(variable=True))
    assert validator.is_valid(variable)
    for methods in (
        [],
        ["bad method"],
        ["PROPFIND\n"],
        ["méthod"],
        ["x" * 129],
        ["PROPFIND", "PROPFIND"],
        ["${route_method}\n"],
    ):
        invalid = yaml.safe_load(_source("GET"))
        invalid["nodes"]["host"]["runtime"]["applications"][0]["routes"][0]["methods"] = methods
        assert not validator.is_valid(invalid)


@pytest.mark.parametrize("contract_id", ["instantiated-scenario-v1", "instantiated-scenario-snapshot-v1"])
def test_concrete_schemas_preserve_extension_identity_and_reject_authoring_syntax(contract_id: str) -> None:
    instantiated = instantiate_scenario(parse_sdl(_source("PROPFIND", "PrivateQuery", "privateQuery")))
    if contract_id == "instantiated-scenario-v1":
        payload = instantiated.model_dump(mode="json", by_alias=True, exclude_none=True)
    else:
        payload = json.loads(canonical_instantiated_sdl_bytes(instantiated))

    validator = Draft202012Validator(schema_bundle()[contract_id])
    assert validator.is_valid(payload)

    for methods in (
        ["${route_method}"],
        ["bad method"],
        ["PROPFIND\n"],
        ["PROPFIND", "PROPFIND"],
    ):
        invalid = deepcopy(payload)
        invalid_scenario = invalid if contract_id == "instantiated-scenario-v1" else invalid["scenario"]
        invalid_scenario["nodes"]["host"]["runtime"]["applications"][0]["routes"][0]["methods"] = methods
        assert not validator.is_valid(invalid)

"""Issues #500/#724: concrete tokens and closed instantiated phase shape.

`sdl-authoring-input-v1` and `instantiated-scenario-v1` were byte-identical
apart from metadata, and the authoring-vs-instantiated distinction relied on
private Python state. These tests pin both repairs: the instantiated contract
rejects unresolved ``${var}`` tokens and all authoring machinery, requires
portable provenance, and has a separately profiled snapshot contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes._base import VARIABLE_TOKEN_PATTERN
from raes.scenario import InstantiatedScenario, Scenario
from raes_contracts.contracts import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
SDL_SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas" / "sdl"
FIXTURE_DIR = REPO_ROOT / "contracts" / "fixtures" / "sdl" / "instantiated-scenario-v1"
SNAPSHOT_FIXTURE_DIR = REPO_ROOT / "contracts" / "fixtures" / "sdl" / "instantiated-scenario-snapshot-v1"

_PROVENANCE = {
    "authored_digest": {
        "profile": "raes-sdl-semantic/v2",
        "algorithm": "sha256",
        "value": "sha256:" + "a" * 64,
    }
}
_CONCRETE = {
    "name": "concrete-scenario",
    "description": "a fully concrete scenario",
    "instantiation_provenance": _PROVENANCE,
}
_EMBEDDED_VAR = {"name": "concrete-scenario", "description": "deploy ${region} cluster"}
_FULL_VAR = {"name": "concrete-scenario", "description": "${environment}"}
_COUNT_VAR = {"name": "concrete-scenario", "infrastructure": {"net": {"count": "${replicas}"}}}
_INVALID_VARIABLE_NAME = {"name": "variable-contract", "variables": {"bad.name": {"type": "string"}}}
_BEHAVIOR_SPEC_EXTENSION_VAR = {
    "name": "concrete-scenario",
    "behavior_specifications": {
        "blue-response": {
            "semantic_version": "1.0.0",
            "participant_refs": ["blue-operator"],
            "action_contract_refs": ["triage"],
            "extensions": {"x-acme:note": {"nested": ["ready", "${secret}"]}},
        }
    },
}

_VAR_PAYLOADS = [_EMBEDDED_VAR, _FULL_VAR, _COUNT_VAR, _BEHAVIOR_SPEC_EXTENSION_VAR]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# The token pattern's backslashes are escaped once serialized into a schema's
# `not.pattern`; match the serialized form, not the raw Python string.
_PATTERN_IN_JSON = json.dumps(VARIABLE_TOKEN_PATTERN)[1:-1]


# --- Model boundary -------------------------------------------------------


@pytest.mark.parametrize("payload", _VAR_PAYLOADS)
def test_authoring_model_accepts_unresolved_variables(payload: dict) -> None:
    """No regression: the authoring model still accepts ``${var}`` placeholders."""
    scenario = Scenario.model_validate(payload)
    assert scenario.name == payload["name"]


def test_instantiated_model_accepts_concrete_scenario() -> None:
    instantiated = InstantiatedScenario.model_validate(_CONCRETE)
    assert instantiated.name == "concrete-scenario"


def test_authoring_model_rejects_invalid_variable_name() -> None:
    with pytest.raises(ValidationError):
        Scenario.model_validate(_INVALID_VARIABLE_NAME)


@pytest.mark.parametrize("payload", _VAR_PAYLOADS)
def test_instantiated_model_rejects_unresolved_variables(payload: dict) -> None:
    with pytest.raises(ValidationError):
        InstantiatedScenario.model_validate({**payload, "instantiation_provenance": _PROVENANCE})


@pytest.mark.parametrize(
    ("field", "value"),
    (("variables", {}), ("imports", []), ("module", None), ("realization", None)),
)
def test_instantiated_model_rejects_authoring_fields_even_when_empty(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InstantiatedScenario.model_validate({**_CONCRETE, field: value})


# --- JSON Schema boundary (live bundle) -----------------------------------


def test_bundle_instantiated_schema_constraints_differ_from_authoring() -> None:
    """Acceptance (a): the schemas differ in *constraints*, not just metadata."""
    bundle = schema_bundle()
    authoring = json.dumps(bundle["sdl-authoring-input-v1"])
    instantiated = json.dumps(bundle["instantiated-scenario-v1"])
    assert instantiated.count(_PATTERN_IN_JSON) > authoring.count(_PATTERN_IN_JSON)


@pytest.mark.parametrize("payload", _VAR_PAYLOADS)
def test_bundle_instantiated_schema_rejects_unresolved_variables(payload: dict) -> None:
    """Acceptance (b): a ``${var}`` payload fails instantiated-schema validation."""
    bundle = schema_bundle()
    instantiated_payload = {**payload, "instantiation_provenance": _PROVENANCE}
    assert not Draft202012Validator(bundle["instantiated-scenario-v1"]).is_valid(instantiated_payload)
    # The same payload is valid against the authoring contract.
    assert Draft202012Validator(bundle["sdl-authoring-input-v1"]).is_valid(payload)


def test_bundle_instantiated_schema_accepts_concrete_scenario() -> None:
    bundle = schema_bundle()
    assert Draft202012Validator(bundle["instantiated-scenario-v1"]).is_valid(_CONCRETE)


@pytest.mark.parametrize(
    "payload",
    (
        {"name": "concrete-scenario"},
        {
            "name": "incomplete-digest",
            "instantiation_provenance": {"authored_digest": {"value": "sha256:" + "a" * 64}},
        },
        {**_CONCRETE, "variables": {}},
        {**_CONCRETE, "imports": []},
        {**_CONCRETE, "module": None},
        {**_CONCRETE, "realization": None},
    ),
)
def test_bundle_instantiated_schema_enforces_closed_phase_shape(payload: dict) -> None:
    assert not Draft202012Validator(schema_bundle()["instantiated-scenario-v1"]).is_valid(payload)


def test_bundle_authoring_schema_rejects_invalid_variable_name() -> None:
    bundle = schema_bundle()
    assert not Draft202012Validator(bundle["sdl-authoring-input-v1"]).is_valid(_INVALID_VARIABLE_NAME)


# --- Published artifacts + fixtures ---------------------------------------


def test_published_schemas_differ_in_constraints() -> None:
    """Acceptance (a) against the published, shipped schema files."""
    authoring = _load(SDL_SCHEMA_DIR / "sdl-authoring-input-v1.json")
    instantiated = _load(SDL_SCHEMA_DIR / "instantiated-scenario-v1.json")
    assert json.dumps(instantiated).count(_PATTERN_IN_JSON) > json.dumps(authoring).count(_PATTERN_IN_JSON)


def test_published_valid_fixture_passes() -> None:
    schema = _load(SDL_SCHEMA_DIR / "instantiated-scenario-v1.json")
    fixture = _load(FIXTURE_DIR / "valid" / "minimal.json")
    assert Draft202012Validator(schema).is_valid(fixture)


def test_published_authoring_schema_rejects_invalid_variable_name() -> None:
    schema = _load(SDL_SCHEMA_DIR / "sdl-authoring-input-v1.json")
    assert not Draft202012Validator(schema).is_valid(_INVALID_VARIABLE_NAME)


def test_published_invalid_fixture_fails() -> None:
    """Acceptance (b), fixture-proven (check_json_artifacts only checks valid/)."""
    schema = _load(SDL_SCHEMA_DIR / "instantiated-scenario-v1.json")
    fixture = _load(FIXTURE_DIR / "invalid" / "unresolved-variable.json")
    assert not Draft202012Validator(schema).is_valid(fixture)
    concrete_control = {**fixture, "description": "deploy concrete cluster"}
    Draft202012Validator(schema).validate(concrete_control)
    # Removing provenance yields the corresponding normalized authoring shape;
    # that shape remains valid because unresolved tokens are authoring syntax.
    authoring = _load(SDL_SCHEMA_DIR / "sdl-authoring-input-v1.json")
    authored_fixture = {key: value for key, value in fixture.items() if key != "instantiation_provenance"}
    Draft202012Validator(authoring).validate(authored_fixture)


@pytest.mark.parametrize(
    "filename",
    ("missing-provenance.json", "variables-empty.json", "imports-empty.json", "module-null.json"),
)
def test_published_phase_invalid_fixtures_fail(filename: str) -> None:
    schema = _load(SDL_SCHEMA_DIR / "instantiated-scenario-v1.json")
    fixture = _load(FIXTURE_DIR / "invalid" / filename)
    assert not Draft202012Validator(schema).is_valid(fixture)


def test_published_snapshot_fixtures_pin_the_profile_boundary() -> None:
    schema = _load(SDL_SCHEMA_DIR / "instantiated-scenario-snapshot-v1.json")
    Draft202012Validator(schema).validate(_load(SNAPSHOT_FIXTURE_DIR / "valid" / "minimal.json"))
    assert not Draft202012Validator(schema).is_valid({"scenario": _CONCRETE})
    assert not Draft202012Validator(schema).is_valid(_load(SNAPSHOT_FIXTURE_DIR / "invalid" / "wrong-profile.json"))

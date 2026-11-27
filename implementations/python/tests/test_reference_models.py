"""Shared reference model catalog tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_contracts.contracts import ReferenceModelCatalogModel
from raes_contracts.reference_models import load_reference_model_catalog, reference_model_catalog_path

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / "contracts" / "concept-authority" / "reference-models-v1.json"
FIXTURES_ROOT = REPO_ROOT / "contracts" / "fixtures" / "concept-authority" / "reference-models-v1"
VALID_DIR = FIXTURES_ROOT / "valid"
INVALID_DIR = FIXTURES_ROOT / "invalid"


def test_load_reference_model_catalog():
    catalog = load_reference_model_catalog()

    assert catalog.schema_version == "reference-models/v1"
    assert set(catalog.models) >= {
        "scenario-node",
        "scenario-account",
        "scenario-relationship",
        "scenario-condition",
        "scenario-event",
        "scenario-content",
    }


def test_reference_model_catalog_path_resolves():
    assert reference_model_catalog_path() == CATALOG_PATH


def test_reference_model_catalog_matches_valid_fixture():
    payload = json.loads((VALID_DIR / "reference.json").read_text(encoding="utf-8"))
    authoritative = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    assert payload == authoritative
    assert ReferenceModelCatalogModel.model_validate(payload).models["scenario-node"].concept_family == "assets"


def test_reference_model_valid_fixtures_pass_validation():
    for path in sorted(VALID_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        model = ReferenceModelCatalogModel.model_validate(payload)
        assert model.models, f"Valid reference model fixture {path.name} should declare models"


def test_reference_model_invalid_fixtures_fail_validation():
    for path in sorted(INVALID_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        with pytest.raises(ValidationError):
            ReferenceModelCatalogModel.model_validate(payload)


def test_reference_model_rejects_unknown_contract_ids():
    payload = json.loads((INVALID_DIR / "unknown-contract-id.json").read_text(encoding="utf-8"))

    with pytest.raises(ValidationError, match="unknown contract ids"):
        ReferenceModelCatalogModel.model_validate(payload)


def test_reference_model_rejects_schema_pointer_mismatches():
    payload = json.loads((INVALID_DIR / "schema-pointer-not-found.json").read_text(encoding="utf-8"))

    with pytest.raises(ValidationError, match="schema_pointer"):
        ReferenceModelCatalogModel.model_validate(payload)


def test_reference_model_rejects_instance_path_mismatches():
    payload = json.loads((INVALID_DIR / "instance-path-mismatch.json").read_text(encoding="utf-8"))

    with pytest.raises(ValidationError, match="instance_path"):
        ReferenceModelCatalogModel.model_validate(payload)


def test_reference_model_rejects_missing_key_fields():
    payload = json.loads((INVALID_DIR / "missing-key-field.json").read_text(encoding="utf-8"))

    with pytest.raises(ValidationError, match="key_fields"):
        ReferenceModelCatalogModel.model_validate(payload)


def test_reference_model_catalog_declares_node_runtime_inventory():
    catalog = load_reference_model_catalog()

    runtime_model = catalog.models["scenario-node-runtime"]
    assert runtime_model.concept_family == "runtime-inventory"
    assert runtime_model.authoritative_schema.contract_id == "sdl-authoring-input-v1"
    assert runtime_model.authoritative_schema.schema_pointer == "#/$defs/RuntimeConfiguration"
    assert runtime_model.authoritative_schema.instance_path == "nodes.*.runtime"
    assert [binding.contract_id for binding in runtime_model.reused_schemas] == ["instantiated-scenario-v1"]
    assert "container" in runtime_model.key_fields


def test_reference_model_binding_resolves_nullable_optional_instance_path():
    # `nodes.*.runtime` is an optional node field (anyOf[RuntimeConfiguration, null]),
    # so binding resolution must look through the nullable-optional wrapper. This is
    # what lets the scenario-node-runtime reference model bind to a real definition.
    from raes_contracts.contracts.catalogs import (
        ReferenceModelSchemaBindingModel,
        validate_reference_model_schema_binding,
    )
    from raes_contracts.contracts.schema_resolution import (
        resolve_instance_path_schema,
        resolve_ref_schema,
        resolve_schema_pointer,
    )
    from raes_schemas import schema_bundle

    root = schema_bundle()["sdl-authoring-input-v1"]
    pointer_schema = resolve_ref_schema(root, resolve_schema_pointer(root, "#/$defs/RuntimeConfiguration"))
    instance_schema = resolve_instance_path_schema(root, "nodes.*.runtime")
    assert pointer_schema == instance_schema

    binding = ReferenceModelSchemaBindingModel(
        contract_id="sdl-authoring-input-v1",
        schema_pointer="#/$defs/RuntimeConfiguration",
        instance_path="nodes.*.runtime",
    )
    # Must not raise: the nullable-optional surface resolves to the real definition.
    validate_reference_model_schema_binding(
        model_id="scenario-node-runtime",
        binding_label="authoritative_schema",
        binding=binding,
        key_fields=["container"],
    )


def test_collapse_nullable_optional_schema_is_conservative():
    from raes_contracts.contracts.schema_resolution import collapse_nullable_optional_schema, resolve_ref_schema

    ref_branch = {"$ref": "#/$defs/RuntimeConfiguration"}
    nullable = {"anyOf": [ref_branch, {"type": "null"}], "default": None}
    assert collapse_nullable_optional_schema(nullable) is ref_branch

    # Non-nullable and non-optional unions are returned unchanged.
    plain = {"type": "object", "properties": {}}
    assert collapse_nullable_optional_schema(plain) is plain
    union = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert collapse_nullable_optional_schema(union) is union

    # The resolver follows the wrapper through to the referenced definition.
    root = {"$defs": {"Thing": {"type": "object", "properties": {"x": {"type": "string"}}}}}
    resolved = resolve_ref_schema(root, {"anyOf": [{"$ref": "#/$defs/Thing"}, {"type": "null"}]})
    assert resolved == root["$defs"]["Thing"]

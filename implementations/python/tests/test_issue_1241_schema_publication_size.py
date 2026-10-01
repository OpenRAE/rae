"""The self-contained attestation schema fits the repository publication budget."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.contracts import schema_bundle


def test_published_materialized_schema_fits_the_existing_file_budget():
    root = Path(__file__).resolve().parents[3]
    path = root / "contracts/schemas/sdl/materialized-scenario-v1.json"
    assert path.stat().st_size <= 500 * 1024
    assert json.loads(path.read_text()) == schema_bundle()["materialized-scenario-v1"]


def test_shared_rules_expand_to_the_exact_unfactored_schema(monkeypatch):
    from raes_contracts.contracts import bundle

    actual = schema_bundle()["materialized-scenario-v1"]
    with monkeypatch.context() as patch:
        patch.setattr(bundle, "factor_shared_schema", deepcopy)
        original = bundle._schema_bundle_template.__wrapped__()["materialized-scenario-v1"]
    added = set(actual["$defs"]) - set(original["$defs"])
    assert added
    refs = {f"#/$defs/{name}": actual["$defs"][name] for name in added}

    def expand(node):
        if isinstance(node, list):
            return [expand(value) for value in node]
        if not isinstance(node, dict):
            return node
        if set(node) == {"$ref"} and node["$ref"] in refs:
            return expand(refs[node["$ref"]])
        return {key: expand(value) for key, value in node.items()}

    without_shared = deepcopy(actual)
    without_shared["$defs"] = {name: value for name, value in actual["$defs"].items() if name not in added}
    assert expand(without_shared) == original


def test_factoring_preserves_instance_data_and_existing_definition_names():
    from raes_contracts.contracts.schema_factoring import factor_shared_schema

    rule = {"type": "string", "maxLength": 10, "description": "Repeated schema documentation " * 4}
    source = {
        "$defs": {"_r0": {"const": "retained"}},
        "type": "object",
        "properties": {"first": rule, "second": rule},
        "default": {"first": rule},
    }
    original = deepcopy(source)
    factored = factor_shared_schema(source)
    assert source == original
    assert factored["default"] == source["default"]
    assert factored["$defs"]["_r0"] == source["$defs"]["_r0"]
    assert factored["properties"]["first"] == factored["properties"]["second"]
    assert "$ref" in factored["properties"]["first"]
    for instance in [{}, {"first": "valid"}, {"second": "too long a value"}, {"first": 42}, [], None]:
        assert Draft202012Validator(factored).is_valid(instance) == Draft202012Validator(source).is_valid(instance)


@pytest.mark.parametrize("keyword", ["$id", "$anchor", "$dynamicAnchor", "$dynamicRef"])
def test_factoring_refuses_nested_reference_scopes(keyword):
    from raes_contracts.contracts.schema_factoring import factor_shared_schema

    with pytest.raises(ValueError, match="anchor-free"):
        factor_shared_schema({"$defs": {"nested": {keyword: "other", "type": "string"}}})

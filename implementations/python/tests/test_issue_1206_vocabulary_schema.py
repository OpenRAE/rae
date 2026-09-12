"""Model and published schema consumers agree on disposed identity fields."""

import json
from enum import Enum
from pathlib import Path
from typing import get_args, get_origin

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, TypeAdapter, ValidationError
from raes.scenario import Scenario
from test_issue_1206_vocabulary_families import _IDENTITIES

_NAMES = {name for _, name in _IDENTITIES} | {"OSFamily", "ImageAttestationType"}


def _types(annotation):
    yield annotation
    for child in get_args(annotation):
        yield from _types(child)


def _identity_fields(*, closed=False):
    pending = [Scenario]
    seen = set()
    fields = []
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for name, field in model.model_fields.items():
            types = tuple(_types(field.annotation))
            pending.extend(t for t in types if isinstance(t, type) and issubclass(t, BaseModel))
            if any(
                isinstance(t, type)
                and issubclass(t, Enum)
                and (
                    t.__name__ in _NAMES
                    if not closed
                    else t.__name__ not in _NAMES
                    and (t.__module__.startswith("raes.runtime_") or t.__module__ == "raes.image_provenance")
                )
                for t in types
            ):
                fields.append((model.__name__, name, field))
    return fields


@pytest.mark.parametrize(
    "model,name,field", _identity_fields(), ids=lambda value: value if isinstance(value, str) else None
)
def test_every_identity_field_has_matching_python_and_schema_grammar(model, name, field):
    adapter = TypeAdapter(field.rebuild_annotation())
    validator = Draft202012Validator(adapter.json_schema())
    sequence = get_origin(field.annotation) is list
    for token, accepted in (
        ("x-owner:private", True),
        ("x-owner:second", True),
        ("invalid-private", False),
        ("x-owner:private\n", False),
    ):
        value = [token] if sequence else token
        if accepted:
            parsed = adapter.validate_python(value)
            assert adapter.dump_python(parsed, mode="json") == value, (model, name)
        else:
            with pytest.raises(ValidationError):
                adapter.validate_python(value)
        assert validator.is_valid(value) is accepted, (model, name)


@pytest.mark.parametrize("model,name,field", _identity_fields(closed=True))
def test_retained_runtime_semantics_reject_new_operations_in_python_and_schema(model, name, field):
    adapter = TypeAdapter(field.rebuild_annotation())
    value = ["x-owner:operation"] if get_origin(field.annotation) is list else "x-owner:operation"
    with pytest.raises(ValidationError):
        adapter.validate_python(value)
    assert not Draft202012Validator(adapter.json_schema()).is_valid(value), (model, name)


def test_published_sdl_schema_rejects_malformed_private_engine():
    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / "contracts/schemas/sdl/instantiated-scenario-v1.json").read_text())
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/RuntimeDatabaseService"})
    assert validator.is_valid({"database_service_id": "database", "engine": "x-owner:private"})
    assert not validator.is_valid({"database_service_id": "database", "engine": "invalid-private"})

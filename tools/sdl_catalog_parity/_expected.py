"""Expected catalog classifications derived from the live SDL model."""

from __future__ import annotations

from typing import Any

from raes._runtime_service_families import RuntimeReferenceChild
from raes.scenario import ExpandedScenario, InstantiatedScenario, Scenario

from tools.policy.common import PolicyFailure
from tools.sdl_catalog_parity._paths import _COMPOSITION_FIELDS, _METADATA_FIELDS

_SCHEMA_TYPE_SHAPES = {
    "string": "scalar",
    "array": "list",
    "object": "map",
}
_DEFAULT_PRESENCE_LABELS = (
    ("*", "optional; default `*`"),
    ("", "optional; default empty string"),
    (None, "optional; default null"),
    ([], "optional; default empty list"),
    ({}, "optional; default empty map"),
)
_FIELD_IDENTITIES = {
    "name": "scenario_name",
    "module": "module.id",
    "imports": "namespace",
    "forwarding_agents": "forwarding_agent_id",
}


def _failure(rule_id: str, message: str, path: str) -> PolicyFailure:
    return PolicyFailure(rule_id, message, path)


def _expected_kind(field: str) -> str:
    if field in _METADATA_FIELDS:
        return "metadata"
    if field in _COMPOSITION_FIELDS:
        return "composition"
    return "section"


def _schema_shape(schema: dict[str, Any]) -> str:
    if "anyOf" in schema:
        nonnull = [branch for branch in schema["anyOf"] if branch.get("type") != "null"]
        if len(nonnull) == 1:
            return _schema_shape(nonnull[0])
    schema_type = schema.get("type")
    shape = "unknown"
    if schema_type is None and schema.get("default") is None:
        shape = "mapping"
    elif isinstance(schema_type, str):
        shape = _SCHEMA_TYPE_SHAPES.get(schema_type, "unknown")
    return shape


def _expected_presence(field: str) -> str:
    model_field = Scenario.model_fields[field]
    if model_field.is_required():
        return "required"
    value = model_field.default_factory() if model_field.default_factory is not None else model_field.default
    label = next(
        (label for sentinel, label in _DEFAULT_PRESENCE_LABELS if value == sentinel),
        None,
    )
    return label if label is not None else f"optional; default `{value}`"


def _expected_identity(field: str, shape: str) -> str:
    fallback = "map_key" if shape == "map" else "none"
    return _FIELD_IDENTITIES.get(field, fallback)


def _expected_lifecycle(field: str) -> tuple[str, ...]:
    phase_models = (
        ("normalized", Scenario),
        ("expanded", ExpandedScenario),
        ("instantiated", InstantiatedScenario),
    )
    return tuple(phase for phase, model in phase_models if field in model.model_fields)


def _flatten_children(children: tuple[RuntimeReferenceChild, ...], prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    for child in children:
        path = (
            f"{prefix}/{child.collection_name}:{child.id_field}"
            if prefix
            else f"{child.collection_name}:{child.id_field}"
        )
        paths.append(path)
        paths.extend(_flatten_children(child.children, path))
    return tuple(paths)

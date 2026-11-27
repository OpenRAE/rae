"""Resolve JSON Schema references and instance paths inside one schema document.

``resolve_schema_pointer`` follows a local ``#/`` pointer (RFC 6901 tokens),
``resolve_ref_schema`` follows ``$ref`` chains and looks through a nullable
optional wrapper, and ``resolve_instance_path_schema`` walks a dotted instance
path where ``*`` names the ``additionalProperties`` schema.
"""

from __future__ import annotations

from typing import Any

from ..json_pointer import unescape_token


def resolve_schema_pointer(schema_root: dict[str, Any], pointer: str) -> dict[str, Any]:
    if not pointer.startswith("#/"):
        raise KeyError(pointer)

    current: object = schema_root
    for raw_segment in pointer[2:].split("/"):
        segment = unescape_token(raw_segment)
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(pointer)
        current = current[segment]

    if not isinstance(current, dict):
        raise KeyError(pointer)
    return current


def collapse_nullable_optional_schema(schema_node: dict[str, Any]) -> dict[str, Any]:
    """Collapse a nullable-optional ``anyOf`` wrapper to its single non-null branch.

    Pydantic renders an optional reference field (``X | None``) as a two-member
    ``anyOf`` whose branches are the referenced schema and ``{"type": "null"}``.
    Reference-model bindings address the underlying structure, so the resolver
    looks through that wrapper (for example ``nodes.*.runtime``, an optional
    ``RuntimeConfiguration``). Anything that is not exactly this nullable-optional
    shape is returned unchanged, so non-optional and non-reference schemas are
    unaffected.
    """
    any_of = schema_node.get("anyOf")
    if not isinstance(any_of, list) or len(any_of) != 2:
        return schema_node
    non_null = [branch for branch in any_of if not (isinstance(branch, dict) and branch.get("type") == "null")]
    null_branches = [branch for branch in any_of if isinstance(branch, dict) and branch.get("type") == "null"]
    if len(non_null) == 1 and len(null_branches) == 1 and isinstance(non_null[0], dict):
        return non_null[0]
    return schema_node


def resolve_ref_schema(schema_root: dict[str, Any], schema_node: dict[str, Any]) -> dict[str, Any]:
    current = schema_node
    while True:
        if "$ref" in current:
            ref = current["$ref"]
            if not isinstance(ref, str):
                raise KeyError(ref)
            current = resolve_schema_pointer(schema_root, ref)
            continue
        collapsed = collapse_nullable_optional_schema(current)
        if collapsed is not current:
            current = collapsed
            continue
        return current


def resolve_instance_path_schema(schema_root: dict[str, Any], instance_path: str) -> dict[str, Any]:
    current = schema_root
    for segment in instance_path.split("."):
        current = resolve_ref_schema(schema_root, current)
        if segment == "*":
            additional_properties = current.get("additionalProperties")
            if not isinstance(additional_properties, dict):
                raise KeyError(instance_path)
            current = additional_properties
            continue

        properties = current.get("properties")
        if not isinstance(properties, dict) or segment not in properties or not isinstance(properties[segment], dict):
            raise KeyError(instance_path)
        current = properties[segment]
    return resolve_ref_schema(schema_root, current)


__all__ = [
    "collapse_nullable_optional_schema",
    "resolve_instance_path_schema",
    "resolve_ref_schema",
    "resolve_schema_pointer",
]

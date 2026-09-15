"""Lossless local factoring of repeated schemas, never instance data or text."""

import json
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from .schema_invariants import _SCHEMA_MAP_KEYS, _SCHEMA_SUBSCHEMA_KEYS

_DEFINITIONS = "$defs"


def _map_children(node: dict[str, Any], transform: Callable[[Any, bool], Any]) -> dict[str, Any]:
    result = deepcopy(node)
    for key in _SCHEMA_MAP_KEYS:
        if isinstance(result.get(key), dict):
            result[key] = {name: transform(value, key == _DEFINITIONS) for name, value in result[key].items()}
    for key in _SCHEMA_SUBSCHEMA_KEYS:
        value = result.get(key)
        if isinstance(value, list):
            result[key] = [transform(child, False) for child in value]
        elif isinstance(value, dict):
            result[key] = transform(value, False)
    return result


def _shared_names(counts: Counter[str], candidates: dict[str, dict[str, Any]], existing: set[str]) -> dict[str, str]:
    names = {}
    index = 0
    for key in sorted(counts):
        if counts[key] < 2 or len(key) < 80 or "$ref" in candidates[key]:
            continue
        while f"_r{index}" in existing:
            index += 1
        names[key] = f"_r{index}"
        existing.add(names[key])
        index += 1
    return names


def factor_shared_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Share exact repeated subschemas inside a single local-reference resource.

    Original named definitions, annotations and data-valued keywords remain
    intact. Resource identifiers and anchors are refused rather than relocated.
    Factoring changes only representation, not the schema's admitted instances.
    """
    counts: Counter[str] = Counter()
    candidates: dict[str, dict[str, Any]] = {}

    def key_of(node: Any) -> str:
        return json.dumps(node, sort_keys=True, separators=(",", ":"))

    def count(node: Any, root: bool = False) -> Any:
        if not isinstance(node, dict):
            return node
        if not root and {"$id", "$anchor", "$dynamicAnchor", "$dynamicRef"} & node.keys():
            raise ValueError("Schema factoring requires one anchor-free resource")
        key = key_of(node)
        counts[key] += 1
        candidates[key] = node
        _map_children(node, lambda child, _preserve: count(child))
        return node

    count(schema, True)
    names = _shared_names(counts, candidates, set(schema.get(_DEFINITIONS, {})))
    shared: dict[str, Any] = {}

    def replace(node: Any, preserve: bool = False) -> Any:
        if not isinstance(node, dict):
            return node
        key = key_of(node)
        if not preserve and key in names:
            name = names[key]
            if name not in shared:
                shared[name] = replace(node, True)
            return {"$ref": f"#/$defs/{name}"}
        return _map_children(node, replace)

    result = replace(schema, True)
    result.setdefault(_DEFINITIONS, {}).update(shared)
    return result

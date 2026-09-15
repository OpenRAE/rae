"""Lossless local factoring of repeated schemas, never instance data or text."""

import json
from collections import Counter
from copy import deepcopy

from .schema_invariants import _SCHEMA_MAP_KEYS, _SCHEMA_SUBSCHEMA_KEYS


def _map_children(node, transform):
    result = deepcopy(node)
    for key in _SCHEMA_MAP_KEYS:
        if isinstance(result.get(key), dict):
            result[key] = {name: transform(value, key == "$defs") for name, value in result[key].items()}
    for key in _SCHEMA_SUBSCHEMA_KEYS:
        value = result.get(key)
        if isinstance(value, list):
            result[key] = [transform(child, False) for child in value]
        elif isinstance(value, dict):
            result[key] = transform(value, False)
    return result


def factor_shared_schema(schema):
    """Share exact repeated subschemas inside a single local-reference resource.

    Original named definitions, annotations and data-valued keywords remain
    intact. Resource identifiers and anchors are refused rather than relocated.
    Factoring changes only representation, not the schema's admitted instances.
    """
    counts = Counter()
    candidates = {}

    def key_of(node):
        return json.dumps(node, sort_keys=True, separators=(",", ":"))

    def count(node, root=False):
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
    existing = set(schema.get("$defs", {}))
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
    shared = {}

    def replace(node, preserve=False):
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
    result.setdefault("$defs", {}).update(shared)
    return result

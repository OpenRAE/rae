"""Empty-default cleanup at the versioned instantiated-snapshot boundary.

This is not assertion migration. Any nonempty retired surface remains present
and is rejected by current model admission with explicit migration guidance.
"""

from __future__ import annotations

from typing import Any


def _remove_empty(item: object, fields: tuple[str, ...], empty: object) -> bool:
    changed = False
    if isinstance(item, dict):
        for field in fields:
            if field in item and type(item[field]) is type(empty) and item[field] == empty:
                del item[field]
                changed = True
    return changed


def _entities(values: object) -> bool:
    changed = False
    if isinstance(values, dict):
        for item in values.values():
            changed |= _remove_empty(item, ("vulnerabilities", "categories"), [])
            if isinstance(item, dict):
                changed |= _entities(item.get("entities"))
    return changed


def remove_empty_legacy_snapshot_classifications(scenario: dict[str, Any]) -> bool:
    """Remove only exact empty containers materialized by historical defaults."""
    changed = _remove_empty(scenario, ("vulnerabilities",), {})
    for section, fields in (
        ("nodes", ("vulnerabilities",)),
        ("features", ("vulnerabilities",)),
        ("action_contracts", ("external_mappings",)),
        (
            "behavior_specifications",
            ("offensive_behavior_refs", "ai_offensive_behavior_refs", "defensive_behavior_refs"),
        ),
    ):
        values = scenario.get(section)
        if isinstance(values, dict):
            for item in values.values():
                changed |= _remove_empty(item, fields, [])
    changed |= _entities(scenario.get("entities"))
    nodes = scenario.get("nodes")
    if not isinstance(nodes, dict):
        return changed
    for node in nodes.values():
        runtime = node.get("runtime") if isinstance(node, dict) else None
        applications = runtime.get("applications") if isinstance(runtime, dict) else None
        if not isinstance(applications, list):
            continue
        for application in applications:
            routes = application.get("routes") if isinstance(application, dict) else None
            if isinstance(routes, list):
                for route in routes:
                    changed |= _remove_empty(route, ("vulnerability_refs",), [])
    return changed

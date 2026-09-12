"""Shared helpers for the SDL authoring tools."""

from __future__ import annotations

_SECTION_FIELDS = [
    "nodes",
    "infrastructure",
    "features",
    "conditions",
    "entities",
    "injects",
    "events",
    "scripts",
    "stories",
    "content",
    "accounts",
    "relationships",
    "agents",
    "objectives",
    "workflows",
    "variables",
]


def _section_summary(scenario: object) -> list[tuple[str, int]]:
    """Return (section_name, element_count) for non-empty sections."""
    counts: list[tuple[str, int]] = []
    for field in _SECTION_FIELDS:
        data = getattr(scenario, field, None)
        if data:
            counts.append((field, len(data)))
    return counts

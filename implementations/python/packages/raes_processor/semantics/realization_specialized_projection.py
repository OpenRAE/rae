"""Source-ordered recursive views of incumbent specialized concern semantics.

Comparison-only identities never enter persisted runtime observations. Native
sanitizers continue to own the publication-safe payload shapes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic_core import to_jsonable_python
from raes.runtime_resource_limits import process_resource_limit_identity_digest
from raes_contracts.canonical import canonical_json_digest, jsonable_fallback

from .realization_concern_projections import (
    project_capability_policy,
    project_forwarding_agents,
    project_mounts,
    project_process_resource_limits,
    project_published_ports,
    project_service_listeners,
)

_CAPABILITY_IDENTITY_FIELDS = frozenset({"required", "effective", "add", "drop", "process_overrides"})
_FORWARDING_IDENTITY_KEYS = {
    "sources": "source_id",
    "transforms": "transform_id",
    "ship_targets": "target_id",
    "reload_channels": "reload_channel_id",
    "settings": "setting_id",
}


def recursive_mounts(value: object, observed: bool = False) -> object:
    entries = []
    for item in to_jsonable_python(value, fallback=jsonable_fallback):
        for entry in project_mounts([item], observed):
            entry["options"] = _scalar_set(item.get("options", []))
            entries.append(entry)
    return entries


def _scalar_set(values: Iterable[object]) -> list[dict[str, object]]:
    return [{"_identity": value, "value": value} for value in values]


def recursive_ports(value: object, observed: bool = False) -> object:
    return [
        project_published_ports([item], observed)[0] for item in to_jsonable_python(value, fallback=jsonable_fallback)
    ]


def recursive_listeners(value: object, observed: bool = False) -> object:
    return [
        project_service_listeners([item], observed)[0] for item in to_jsonable_python(value, fallback=jsonable_fallback)
    ]


def recursive_process_limits(value: object, observed: bool = False) -> object:
    return [
        {
            **project_process_resource_limits([item], observed)[0],
            "_identity": process_resource_limit_identity_digest(item),
        }
        for item in to_jsonable_python(value, fallback=jsonable_fallback)
    ]


def recursive_capabilities(value: object, observed: bool = False) -> object:
    record = to_jsonable_python(value, fallback=jsonable_fallback)
    projected = project_capability_policy(record, observed)
    for field in ("required", "effective", "add", "drop"):
        projected[field] = _scalar_set(record.get(field, []))
    overrides = []
    for item in record.get("process_overrides", []):
        override = project_capability_policy({"process_overrides": [item]}, observed)["process_overrides"][0]
        override["_identity"] = canonical_json_digest(override["subject"])
        for field in ("effective", "add", "drop"):
            override[field] = _scalar_set(item.get(field, []))
        overrides.append(override)
    projected["process_overrides"] = overrides
    return projected


def recursive_forwarding(value: object, observed: bool = False) -> object:
    agents = []
    for item in to_jsonable_python(value, fallback=jsonable_fallback):
        agent = project_forwarding_agents([item], observed)[0]
        for field in ("sources", "transforms", "ship_targets", "reload_channels", "settings"):
            agent[field] = [
                project_forwarding_agents([{**item, field: [child]}], observed)[0][field][0]
                for child in item.get(field, [])
            ]
        agents.append(agent)
    return agents


def _specialized_identity_key(kind: str, field: str) -> str | None:
    """Name the identity field one concern assigns to a nested collection."""

    if kind == "runtime-software-components" and field == "repository_refs":
        key = "_identity"
    elif kind == "runtime-repository-state":
        key = {"repositories": "repository_id", "trust_bindings": "trust_id"}.get(field)
    elif (kind == "linux-capabilities" and field in _CAPABILITY_IDENTITY_FIELDS) or (
        kind == "runtime-mounts" and field == "options"
    ):
        key = "_identity"
    else:
        key = _FORWARDING_IDENTITY_KEYS.get(field) if kind == "forwarding-agents" else None
    return key


def specialized_collection_identity(kind: str, pointer: str) -> tuple[str, ...]:
    """Nested identity belongs to the concern, never inferred from backend data."""

    key = _specialized_identity_key(kind, pointer.rsplit("/", 1)[-1])
    keys = [] if key is None else [key]
    return tuple(keys)


def source_occurrences(
    kind: str, pointer: str, projected: list[object], source: list[object]
) -> list[tuple[int, object]]:
    """Retain source indices across the incumbent mount filter and scalar sort."""

    occurrences = list(enumerate(source))
    if kind == "runtime-mounts" and not pointer:
        occurrences = [
            (index, item)
            for index, item in occurrences
            if (item.get("source_kind") if isinstance(item, Mapping) else item.source_kind) in {"bind", "tmpfs"}
        ]
    if len(occurrences) == len(projected) and all(not isinstance(item, (dict, list)) for item in projected):
        raw = to_jsonable_python([item for _, item in occurrences], fallback=jsonable_fallback)
        if sorted(raw, key=canonical_json_digest) == sorted(projected, key=canonical_json_digest):
            unused = list(occurrences)
            ordered = []
            for item in projected:
                index = next(
                    i
                    for i, (_, candidate) in enumerate(unused)
                    if to_jsonable_python(candidate, fallback=jsonable_fallback) == item
                )
                ordered.append(unused.pop(index))
            return ordered
    return occurrences


def native_process_limit_projection(
    projection: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    return [{key: value for key, value in item.items() if key != "_identity"} for item in projection]

"""Value-free differences over the common SDL content and its native identities."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any, TypeAlias

from raes.explicitness import ExplicitnessProvenance
from raes.materialization import MaterializedScenario
from raes.materialization_provenance import MaterializationOrigin
from raes.nodes import Node
from raes.runtime_inventory import runtime_inventory_collection_identity
from raes.scenario import InstantiatedScenario, ScenarioContent
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

from ..semantics.realization_concerns import registered_realization_concern_descriptors

_ABSENT = object()
_CollectionProfiles: TypeAlias = dict[tuple[str, ...], tuple[str, ...]]


def materialization_differences(
    source: InstantiatedScenario,
    materialized: MaterializedScenario,
) -> tuple[MaterializationOrigin, ...]:
    """Find changes without treating a containing authored node as an addition."""
    for value in (source, materialized):
        content = {name: getattr(value, name) for name in ScenarioContent.model_fields}
        if not validate_realization_value(
            content, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True
        ).conformant:
            raise ValueError("materialization comparison exceeds portable bounds")
    before = source.model_dump(mode="json", exclude={"instantiation_provenance"})
    after = materialized.model_dump(mode="json", exclude={"materialization_provenance"})
    profiles = _profiles(
        before["nodes"].keys() | after["nodes"].keys(), before["content"].keys() | after["content"].keys()
    )
    return tuple(_differences(before, after, (), (), profiles))


def _profiles(node_names: Iterable[str], content_names: Iterable[str]) -> _CollectionProfiles:
    return {
        (
            item.descriptor.section,
            item.declaration_name,
            *item.descriptor.authored_path,
        ): item.descriptor.collection_identity_fields
        for item in registered_realization_concern_descriptors(
            declaration_names={
                "nodes": node_names,
                "content": content_names,
            }
        )
        if item.descriptor.collection_identity_fields
    }


def materialization_node_payloads_match(name: str, described: object, observed: object) -> bool:
    """Compare native node fields with shared defaults and keyed identities.

    This is a local inventory comparison, never reconstruction of source SDL
    or a substitute for the runtime's corroboration and authority checks.
    """
    if not validate_realization_value([described, observed], limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant:
        return False
    try:
        left = Node.model_validate(described).model_dump(mode="json")
        right = Node.model_validate(observed).model_dump(mode="json")
        path = ("nodes", name)
        return not any(_differences(left, right, path, path, _profiles({name}, set())))
    except (TypeError, ValueError):
        return False


def validate_materialization_origins(source: InstantiatedScenario, materialized: MaterializedScenario) -> None:
    """Require exact value-free coverage, rejecting missing or relabelled origins."""
    actual = {item.model_dump_json() for item in materialization_differences(source, materialized)}
    claimed = {item.model_dump_json() for item in materialized.materialization_provenance.origins}
    if actual != claimed:
        raise ValueError("materialization origins do not exactly account for the source differences")


def _pointer(tokens: tuple[str, ...]) -> str:
    return "".join("/" + token.replace("~", "~0").replace("/", "~1") for token in tokens)


def _origin(change: str, before_path: tuple[str, ...], after_path: tuple[str, ...]) -> MaterializationOrigin:
    return MaterializationOrigin(
        field_pointer=_pointer(before_path if change == "removed" else after_path),
        source_pointer=None if change == "added" else _pointer(before_path),
        change=change,
        origin=ExplicitnessProvenance.BACKEND_REALIZED,
    )


def _collection_identity(path: tuple[str, ...], profiles: _CollectionProfiles) -> tuple[str, ...]:
    identity = ()
    if path in profiles:
        identity = profiles[path]
    elif len(path) == 3 and path[0] == "nodes" and path[2] == "services":
        identity = ("name",)
    elif len(path) >= 4 and path[0] == "nodes" and path[2] == "runtime":
        identity = runtime_inventory_collection_identity(path[3].replace("_", "-"), _pointer(path[4:]))
    return identity


def _indexed(values: list[object], identity: tuple[str, ...]) -> dict[str, tuple[int, object]]:
    result = {}
    for index, value in enumerate(values):
        if not isinstance(value, dict) or any(field not in value for field in identity):
            raise ValueError("materialization inventory lacks its owning collection identity")
        key = canonical_json_digest({field: value[field] for field in identity})
        if key in result:
            raise ValueError("materialization inventory has duplicate collection identities")
        result[key] = (index, value)
    return result


def _differences(
    before: object,
    after: object,
    before_path: tuple[str, ...],
    after_path: tuple[str, ...],
    profiles: _CollectionProfiles,
) -> Iterator[MaterializationOrigin]:
    if isinstance(before, dict) and isinstance(after, dict):
        yield from _mapping_differences(before, after, before_path, after_path, profiles)
    elif isinstance(before, list) and isinstance(after, list):
        yield from _sequence_differences(before, after, before_path, after_path, profiles)
    elif change := _leaf_change(before, after):
        yield _origin(change, before_path, after_path)


def _leaf_change(before: object, after: object) -> str | None:
    change = None
    if before is _ABSENT:
        change = "added"
    elif after is _ABSENT:
        change = "removed"
    elif type(before) is not type(after) or before != after:
        change = "selected"
    return change


def _mapping_differences(
    before: dict[str, Any],
    after: dict[str, Any],
    before_path: tuple[str, ...],
    after_path: tuple[str, ...],
    profiles: _CollectionProfiles,
) -> Iterator[MaterializationOrigin]:
    for key in sorted(before.keys() | after.keys()):
        yield from _differences(
            before.get(key, _ABSENT),
            after.get(key, _ABSENT),
            (*before_path, key),
            (*after_path, key),
            profiles,
        )


def _sequence_differences(
    before: list[object],
    after: list[object],
    before_path: tuple[str, ...],
    after_path: tuple[str, ...],
    profiles: _CollectionProfiles,
) -> Iterator[MaterializationOrigin]:
    identity = _collection_identity(after_path, profiles)
    if identity:
        yield from _keyed_differences(
            _indexed(before, identity), _indexed(after, identity), before_path, after_path, profiles
        )
    else:
        for index in range(max(len(before), len(after))):
            yield from _differences(
                before[index] if index < len(before) else _ABSENT,
                after[index] if index < len(after) else _ABSENT,
                (*before_path, str(index)),
                (*after_path, str(index)),
                profiles,
            )


def _keyed_differences(
    left: dict[str, tuple[int, object]],
    right: dict[str, tuple[int, object]],
    before_path: tuple[str, ...],
    after_path: tuple[str, ...],
    profiles: _CollectionProfiles,
) -> Iterator[MaterializationOrigin]:
    for key in sorted(left.keys() | right.keys()):
        left_index, left_value = left.get(key, (0, _ABSENT))
        right_index, right_value = right.get(key, (0, _ABSENT))
        yield from _differences(
            left_value,
            right_value,
            (*before_path, str(left_index)),
            (*after_path, str(right_index)),
            profiles,
        )


__all__ = ["materialization_differences", "materialization_node_payloads_match", "validate_materialization_origins"]

"""Apply exact author decisions through native model-owned sentinel fields."""

from enum import Enum
from typing import Any

from pydantic import BaseModel
from raes_contracts.sdl_semantic_migration import SDLSentinelDecision
from raes_contracts.vocabulary import Closure

from .realization_designation import RealizationDesignationRecord, designation_records, resolve_realization_designation
from .scenario import Scenario


def _token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def sentinel_pointers(value: object, pointer: str = "") -> set[str]:
    """Inspect typed enum leaves; arbitrary strings/private JSON are not sentinels."""
    if isinstance(value, Enum):
        return {pointer} if value.value in {"unknown", "other"} else set()
    found: set[str] = set()
    if isinstance(value, BaseModel):
        for name in value.model_fields_set:
            field = type(value).model_fields[name]
            key = field.serialization_alias or field.alias or name
            found.update(sentinel_pointers(getattr(value, name), f"{pointer}/{_token(key)}"))
    elif isinstance(value, dict):
        for key, child in value.items():
            found.update(sentinel_pointers(child, f"{pointer}/{_token(key)}"))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found.update(sentinel_pointers(child, f"{pointer}/{index}"))
    return found


def apply_sentinel_decisions(
    scenario: Scenario, decisions: tuple[SDLSentinelDecision, ...]
) -> tuple[dict[str, object] | None, str | None]:
    pointers = sentinel_pointers(scenario)
    if pointers != {decision.pointer for decision in decisions}:
        return None, "semantic-migration.sentinel-decision-required"
    payload = scenario.model_dump(mode="json", by_alias=True, exclude_unset=True)
    records = designation_records(scenario.realization) if scenario.realization is not None else ()
    list_deletions: list[tuple[list[Any], int]] = []
    for decision in decisions:
        code = _apply_decision(payload, decision, records, list_deletions)
        if code is not None:
            return None, code
    # Decisions address the original source; removals must not shift later targets.
    for parent, index in sorted(list_deletions, key=lambda deletion: deletion[1], reverse=True):
        del parent[index]
    return payload, None


def _decision_parent(payload: dict[str, Any], pointer: str) -> tuple[Any, str | int]:
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    parent: Any = payload
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
    return parent, key


def _apply_decision(
    payload: dict[str, Any],
    decision: SDLSentinelDecision,
    records: tuple[RealizationDesignationRecord, ...],
    list_deletions: list[tuple[list[Any], int]],
) -> str | None:
    if decision.interpretation == "knowledge":
        return None
    parent, key = _decision_parent(payload, decision.pointer)
    if decision.interpretation == "delegated":
        closure = resolve_realization_designation(records, field_pointer=decision.pointer)
        if closure.closure != Closure.OPEN_WORLD or closure.delegated:
            return "semantic-migration.delegation-needs-open-scope"
        if isinstance(parent, list):
            list_deletions.append((parent, int(key)))
        else:
            del parent[key]
    else:
        parent[key] = decision.identity
    return None

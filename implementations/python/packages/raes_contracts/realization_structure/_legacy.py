"""Compatibility subset used by pre-#1203 planning contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import Field

from ..canonical import canonical_json_digest
from ._common import json_equal
from ._models import StructureModel


class ExactRealizationValue(StructureModel):
    kind: Literal["exact"]


class OpenRealizationValue(StructureModel):
    kind: Literal["open"]
    # These are typed taxonomy spellings, not arbitrary values or domains.
    taxonomy_sentinel: bool = False


class RealizationRecord(StructureModel):
    kind: Literal["record"]
    fields: dict[str, RealizationStructure] = Field(max_length=4096)
    additional: bool = False


class RealizationCollection(StructureModel):
    kind: Literal["collection"]
    identity_fields: tuple[str, ...] = Field(min_length=1, max_length=8)
    members: dict[Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")], RealizationStructure] = Field(
        max_length=4096
    )
    additional: bool = False


RealizationStructure = Annotated[
    ExactRealizationValue | OpenRealizationValue | RealizationRecord | RealizationCollection,
    Field(discriminator="kind"),
]
RealizationRecord.model_rebuild()
RealizationCollection.model_rebuild()


def realization_member_identity(value: object, fields: tuple[str, ...]) -> str | None:
    if not isinstance(value, Mapping):
        return None
    values = tuple(value.get(field) for field in fields)
    if any(type(item) not in (str, int, bool) for item in values):
        return None
    return canonical_json_digest(list(values))


def _record_field_matches(
    key: str,
    child: RealizationStructure,
    expected: dict[str, object],
    actual: dict[str, object],
    depth: int,
    observed: bool,
) -> bool:
    selected_key = key if observed else key.removesuffix("_present").removesuffix("_commitment")
    return (
        selected_key in expected
        and selected_key in actual
        and structure_matches(
            child,
            expected[selected_key],
            actual[selected_key],
            observed=observed,
            _depth=depth + 1,
        )
    )


def _unbound_record_fields_match(
    rule: RealizationRecord,
    expected: dict[str, object],
    actual: dict[str, object],
) -> bool:
    # Unauthored defaults are a closed-scope baseline, not authored leaves.
    return rule.additional or all(
        key in expected and json_equal(expected[key], value) for key, value in actual.items() if key not in rule.fields
    )


def _record_matches(
    rule: RealizationRecord,
    expected: object,
    actual: object,
    depth: int,
    observed: bool,
) -> bool:
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return False
    fields_match = all(
        _record_field_matches(key, child, expected, actual, depth, observed) for key, child in rule.fields.items()
    )
    return fields_match and _unbound_record_fields_match(rule, expected, actual)


def indexed_collection(value: object, fields: tuple[str, ...]) -> dict[str, object] | None:
    if not isinstance(value, list):
        return None
    members = {}
    for item in value:
        identity = realization_member_identity(item, fields)
        if identity is None or identity in members:
            return None
        members[identity] = item
    return members


def _collection_matches(
    rule: RealizationCollection,
    expected: object,
    actual: object,
    depth: int,
    observed: bool,
) -> bool:
    expected_by_id = indexed_collection(expected, rule.identity_fields)
    actual_by_id = indexed_collection(actual, rule.identity_fields)
    if expected_by_id is None or actual_by_id is None:
        return False
    if set(rule.members) != set(expected_by_id) or (not rule.additional and len(expected_by_id) != len(actual_by_id)):
        return False
    return all(
        identity in actual_by_id
        and structure_matches(
            child,
            expected_by_id[identity],
            actual_by_id[identity],
            observed=observed,
            _depth=depth + 1,
        )
        for identity, child in rule.members.items()
    )


def structure_matches(
    rule: RealizationStructure,
    expected: object,
    actual: object,
    *,
    observed: bool = True,
    _depth: int = 0,
) -> bool:
    """Check one observed projection against its admitted baseline and rules."""

    matches = False
    if _depth > 64:
        matches = False
    elif isinstance(rule, ExactRealizationValue):
        matches = json_equal(expected, actual)
    elif isinstance(rule, OpenRealizationValue):
        matches = not observed or not (rule.taxonomy_sentinel and actual in (None, "unknown", "other"))
    elif isinstance(rule, RealizationRecord):
        matches = _record_matches(rule, expected, actual, _depth, observed)
    else:
        matches = _collection_matches(rule, expected, actual, _depth, observed)
    return matches

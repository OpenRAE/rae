"""Finite collection choices use the shared relation's explicit identity aliases."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import product

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.realization_structure import RealizationIdentityAlias

_MAX_IDENTITY_CHOICES = 4096
_ADMITTED_IDENTITY_TYPES = frozenset({str, int, bool})


def _identity_key(identity: Sequence[object]) -> str:
    return canonical_json_digest(list(identity))


def _member_identity_choices(rule: object, member: object) -> tuple[tuple[object, ...], ...] | None:
    """Enumerate the finite identity choices one member's domains admit."""

    child = member.constraint
    if child.kind != "recursive-record":
        return None
    if not any(field in child.fields and child.fields[field].kind == "domain" for field in rule.identity_fields):
        return None
    choices: list[tuple[object, ...]] = []
    for field, original in zip(rule.identity_fields, member.identity, strict=True):
        value = child.fields.get(field)
        if value is None or value.kind != "domain":
            choices.append((original,))
        elif value.domain.kind == "enum":
            choices.append(tuple(value.domain.values))
        else:
            raise ValueError("collection identity domains require finite choices")
    return tuple(choices)


def _record_identity_alias(
    identity: tuple[object, ...],
    member: object,
    identities: dict[str, Sequence[object]],
) -> RealizationIdentityAlias | None:
    """Record one alias, refusing an identity two members could both claim."""

    if any(type(candidate) not in _ADMITTED_IDENTITY_TYPES for candidate in identity):
        raise ValueError("collection choices exceed bounded identity authority")
    key = _identity_key(identity)
    if key in identities:
        if _identity_key(identities[key]) != _identity_key(member.identity):
            raise ValueError("collection domains have ambiguous member identities")
        return None
    identities[key] = member.identity
    return RealizationIdentityAlias(identity=identity, target=member.identity)


def _collection_aliases(
    rule: object, members: tuple[object, ...], budget: list[int]
) -> tuple[RealizationIdentityAlias, ...]:
    """Expand every member's finite identity domains into explicit aliases."""

    aliases: list[RealizationIdentityAlias] = []
    identities = {_identity_key(member.identity): member.identity for member in members}
    for member in members:
        choices = _member_identity_choices(rule, member)
        if choices is None:
            continue
        for identity in product(*choices):
            budget[0] -= 1
            if budget[0] < 0:
                raise ValueError("collection choices exceed bounded identity authority")
            alias = _record_identity_alias(identity, member, identities)
            if alias is not None:
                aliases.append(alias)
    return tuple(aliases)


def _visited_collection(rule: object, visit: Callable[[object], object], budget: list[int]) -> object:
    """Rebuild one keyed collection with visited members and explicit aliases."""

    members = tuple(member.model_copy(update={"constraint": visit(member.constraint)}) for member in rule.members)
    return rule.model_copy(update={"members": members, "aliases": _collection_aliases(rule, members, budget)})


def bind_scalar_set_choices(document: object) -> object:
    """Preserve selected values beside alias identities; refuse ambiguous bounds."""

    budget = [_MAX_IDENTITY_CHOICES]

    def visit(rule: object) -> object:
        if rule.kind == "recursive-record":
            return rule.model_copy(update={"fields": {key: visit(value) for key, value in rule.fields.items()}})
        if rule.kind == "sequence":
            return rule.model_copy(update={"items": tuple(visit(item) for item in rule.items)})
        return _visited_collection(rule, visit, budget) if rule.kind == "keyed-collection" else rule

    return document.model_copy(update={"root": visit(document.root)})

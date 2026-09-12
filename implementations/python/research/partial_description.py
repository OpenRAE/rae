"""Finite design oracle for #1201; neither public SDL nor a production solver.

All quantification is relative to the caller's explicit finite universe. Scope
paths contain semantic identities, never collection positions. The module has
no I/O, extension loading, artifact acquisition, or backend execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Scalar = str | int | bool | None
ABSENT = object()
NO_WITNESS = object()


@dataclass(frozen=True)
class Atom:
    values: tuple[Scalar, ...]


@dataclass(frozen=True)
class Field:
    identity: str
    rule: Atom | Record
    presence: Literal["required", "optional", "absent"] = "required"


@dataclass(frozen=True)
class Record:
    fields: tuple[Field, ...] = ()
    closed: bool = False
    universe: str | None = None
    profile: str | None = None


@dataclass(frozen=True)
class Scope:
    path: tuple[str, ...]
    posture: Literal["open", "closed"] | None


@dataclass
class _Budget:
    remaining: int

    def spend(self, depth: int = 0) -> None:
        self.remaining -= 1
        if self.remaining < 0 or depth > 32:
            raise ValueError("limit-exceeded")


def _scalar(value: object) -> bool:
    return type(value) in (str, int, bool, type(None))


def _validate_rule(rule: Atom | Record, budget: _Budget, depth: int = 0) -> None:
    budget.spend(depth)
    if isinstance(rule, Atom):
        for value in rule.values:
            if not _scalar(value):
                raise ValueError("invalid-atom")
            _validate_value(value, budget, depth)
        return
    if not isinstance(rule, Record):
        raise ValueError("invalid-rule")
    if rule.closed and not rule.universe:
        raise ValueError("closure-universe-required")
    identities: set[str] = set()
    for field in rule.fields:
        if not isinstance(field.identity, str) or not field.identity or len(field.identity) > 256:
            raise ValueError("invalid-identity")
        if field.identity in identities:
            raise ValueError("duplicate-identity")
        identities.add(field.identity)
        if field.presence not in {"required", "optional", "absent"}:
            raise ValueError("invalid-presence")
        _validate_rule(field.rule, budget, depth + 1)


def _validate_value(value: object, budget: _Budget, depth: int = 0) -> None:
    budget.spend(depth)
    if _scalar(value):
        if isinstance(value, str) and len(value) > 4096:
            raise ValueError("limit-exceeded")
        if type(value) is int and value.bit_length() > 256:
            raise ValueError("limit-exceeded")
        return
    if type(value) is not dict:
        raise ValueError("invalid-value")
    for key, child in value.items():
        if type(key) is not str or not key or len(key) > 256:
            raise ValueError("invalid-identity")
        _validate_value(child, budget, depth + 1)


def effective_posture(path: tuple[str, ...], scopes: tuple[Scope, ...], policy: str) -> str:
    """Undefined makes no local statement; callers explicitly select fallback."""
    if policy not in {"open", "closed"}:
        raise ValueError("invalid-policy")
    if len(scopes) > 256:
        raise ValueError("limit-exceeded")
    seen: set[tuple[str, ...]] = set()
    candidates = [(-1, policy)]
    for scope in scopes:
        if scope.path in seen:
            raise ValueError("duplicate-scope")
        seen.add(scope.path)
        if scope.posture not in {None, "open", "closed"}:
            raise ValueError("invalid-posture")
        if scope.posture is not None and path[: len(scope.path)] == scope.path:
            candidates.append((len(scope.path), scope.posture))
    return max(candidates)[1]


def _matches(rule, value, path, budget):
    budget.spend(len(path))
    if isinstance(rule, Atom):
        for item in rule.values:
            budget.spend(len(path))
            if type(value) is type(item) and value == item:
                return True
        return False
    if not isinstance(value, dict):
        return False
    fields = {field.identity: field for field in rule.fields}
    extras = value.keys() - fields.keys()
    if extras and rule.closed:
        return False
    for key, field in fields.items():
        child = value.get(key, ABSENT)
        if child is ABSENT:
            if field.presence == "required":
                return False
        elif field.presence == "absent" or not _matches(field.rule, child, (*path, key), budget):
            return False
    return True


def accepts(rule: Atom | Record, value: object, *, limit: int = 4096) -> bool:
    """Description membership checks constraints, not permission or evidence."""
    budget = _Budget(limit)
    _validate_rule(rule, budget)
    _validate_value(value, budget)
    return _matches(rule, value, (), budget)


def denotation(rules: tuple[Atom | Record, ...], universe: tuple, *, limit: int = 4096) -> frozenset[int]:
    """Conjunction is intersection; indices identify worlds in ONE universe."""
    budget = _Budget(limit)
    for rule in rules:
        _validate_rule(rule, budget)
    members = set()
    for index, value in enumerate(universe):
        _validate_value(value, budget)
        if all(_matches(rule, value, (), budget) for rule in rules):
            members.add(index)
    return frozenset(members)


def _profiles(rule: Atom | Record) -> set[str]:
    if isinstance(rule, Atom):
        return set()
    result = {rule.profile} if rule.profile else set()
    for field in rule.fields:
        result.update(_profiles(field.rule))
    return result


def choose(
    rules: tuple[Atom | Record, ...],
    offered: tuple,
    *,
    scopes: tuple[Scope, ...] = (),
    policy: str = "closed",
    supported_profiles: frozenset[str] = frozenset(),
    limit: int = 4096,
):
    """Select an offered permitted witness; this does not execute a backend."""
    budget = _Budget(limit)
    effective_posture((), scopes, policy)
    for rule in rules:
        _validate_rule(rule, budget)
        if not _profiles(rule) <= supported_profiles:
            raise ValueError("unsupported-semantics")
    declared = set().union(*(_declared_paths(rule) for rule in rules))
    for value in offered:
        _validate_value(value, budget)
        if all(_matches(rule, value, (), budget) for rule in rules) and _permitted(
            value, (), declared, scopes, policy, budget
        ):
            # Normalize/copy the selected finite value: callers cannot mutate the offer.
            return _copy_value(value)
    return NO_WITNESS


def _copy_value(value):
    return {key: _copy_value(child) for key, child in sorted(value.items())} if isinstance(value, dict) else value


def normalize(rule: Atom | Record) -> Atom | Record:
    """Canonical order only: never insert defaults or manufacture observations."""
    _validate_rule(rule, _Budget(4096))
    if isinstance(rule, Atom):
        values = {(type(value).__name__, value): value for value in rule.values}
        return Atom(tuple(values[key] for key in sorted(values, key=lambda key: (key[0], str(key[1])))))
    return Record(
        tuple(
            Field(field.identity, normalize(field.rule), field.presence)
            for field in sorted(rule.fields, key=lambda f: f.identity)
        ),
        rule.closed,
        rule.universe,
        rule.profile,
    )


def resolve_reference(name: str, definitions: dict[str, str | Atom | Record], *, limit: int = 256):
    """Resolve a bounded acyclic local definition chain; never fetch a URI."""
    seen = set()
    budget = _Budget(limit)
    while isinstance(name, str):
        budget.spend()
        if name in seen:
            raise ValueError("reference-cycle")
        seen.add(name)
        if name not in definitions:
            raise ValueError("unknown-reference")
        name = definitions[name]
    _validate_rule(name, _Budget(4096))
    return name


def _declared_paths(rule, path=()):
    result = {path}
    if isinstance(rule, Record):
        for field in rule.fields:
            result.update(_declared_paths(field.rule, (*path, field.identity)))
    return result


def _permitted(value, path, declared, scopes, policy, budget):
    budget.spend(len(path))
    if path not in declared and effective_posture(path, scopes, policy) != "open":
        return False
    return not isinstance(value, dict) or all(
        _permitted(child, (*path, key), declared, scopes, policy, budget) for key, child in value.items()
    )

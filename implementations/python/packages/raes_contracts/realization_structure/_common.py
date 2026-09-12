"""Shared finite-work and diagnostic helpers for realization relations."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum

from pydantic import BaseModel

from ..diagnostics import Diagnostic
from ._models import (
    DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    RealizationClosure,
    RealizationClosurePosture,
    RealizationConstraintDocument,
    RealizationConstraintLimits,
    RealizationRelationStatus,
)


@dataclass
class RelationBudget:
    limits: RealizationConstraintLimits
    python_carriers: bool = False
    nodes: int = 0
    operations: int = 0
    identity_checks: int = 0
    scalar_bytes: int = 0

    def spend_scalar(self, value: object) -> str | None:
        if isinstance(value, str) and len(value) > self.limits.max_scalar_bytes:
            return "max_scalar_bytes"
        try:
            text_bytes = len(value.encode("utf-8")) if isinstance(value, str) else 0
        except UnicodeError:
            return "invalid_utf8"
        size = (
            text_bytes
            if isinstance(value, str)
            else max(1, (value.bit_length() + 7) // 8)
            if type(value) is int
            else 8
            if type(value) in (float, bool, type(None))
            else 0
        )
        if size > self.limits.max_scalar_bytes:
            return "max_scalar_bytes"
        self.scalar_bytes += size
        return "max_total_scalar_bytes" if self.scalar_bytes > self.limits.max_total_scalar_bytes else None

    def spend_node(self, depth: int) -> str | None:
        self.nodes += 1
        if depth > self.limits.max_depth:
            return "max_depth"
        if self.nodes > self.limits.max_nodes:
            return "max_nodes"
        return self.spend_operation()

    def spend_operation(self) -> str | None:
        self.operations += 1
        return "max_operations" if self.operations > self.limits.max_operations else None

    def spend_identity(self) -> str | None:
        self.identity_checks += 1
        return "max_identity_checks" if self.identity_checks > self.limits.max_identity_checks else None


@dataclass(frozen=True)
class RealizationRelationResult:
    """One bounded relation outcome; only ``conformant`` is a success claim."""

    status: RealizationRelationStatus
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def conformant(self) -> bool:
        return self.status is RealizationRelationStatus.CONFORMANT


def combine_relation_results(
    results: list[RealizationRelationResult],
    *,
    max_diagnostics: int,
) -> RealizationRelationResult:
    precedence = (
        RealizationRelationStatus.LIMIT_EXCEEDED,
        RealizationRelationStatus.INVALID,
        RealizationRelationStatus.UNSUPPORTED,
        RealizationRelationStatus.NONCONFORMANT,
        RealizationRelationStatus.UNRESOLVED,
    )
    for status in precedence:
        matching = [result for result in results if result.status is status]
        if matching:
            diagnostics = tuple(diagnostic for result in matching for diagnostic in result.diagnostics)[
                :max_diagnostics
            ]
            return RealizationRelationResult(status, diagnostics)
    return RealizationRelationResult(RealizationRelationStatus.CONFORMANT)


def recursive_diagnostic(code: str, pointer: str, message: str) -> Diagnostic:
    return Diagnostic(code=code, domain="realization", address=pointer, message=message)


def relation_result(status: RealizationRelationStatus, pointer: str, message: str) -> RealizationRelationResult:
    return RealizationRelationResult(
        status,
        (recursive_diagnostic(f"realization.{status.value}", pointer, message),),
    )


def pointer_tokens(pointer: str) -> tuple[str, ...]:
    return tuple(token.replace("~1", "/").replace("~0", "~") for token in pointer.split("/")[1:])


def escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def pointer(path: tuple[str, ...]) -> str:
    return "" if not path else "/" + "/".join(escape_pointer_token(token) for token in path)


def closure_for(
    document: RealizationConstraintDocument,
    local: RealizationClosure,
    path: tuple[str, ...],
    budget: RelationBudget | None = None,
) -> RealizationClosure | None:
    if local.posture is not RealizationClosurePosture.UNDEFINED:
        return local
    candidates = []
    for scope in document.scopes:
        if budget is not None and budget.spend_operation() is not None:
            return None
        tokens = pointer_tokens(scope.field_pointer)
        if tokens == path[: len(tokens)]:
            candidates.append(scope)
    return (
        max(candidates, key=lambda scope: len(pointer_tokens(scope.field_pointer))).closure
        if candidates
        else document.default_closure
    )


def actual_identity(
    item: object,
    identity_fields: tuple[str, ...],
) -> tuple[str | int | bool, ...] | None:
    if not isinstance(item, Mapping):
        return None
    values = tuple(item.get(field) for field in identity_fields)
    if any(type(value) not in (str, int, bool) for value in values):
        return None
    return values  # type: ignore[return-value]


def json_equal(expected: object, actual: object) -> bool:
    """Compare JSON values without Python's bool/int equivalence."""

    if type(expected) is not type(actual):
        equal = False
    elif isinstance(expected, dict) and isinstance(actual, dict):
        equal = _json_dict_equal(expected, actual)
    elif isinstance(expected, list) and isinstance(actual, list):
        equal = _json_list_equal(expected, actual)
    else:
        equal = expected == actual
    return equal


def _json_dict_equal(expected: dict[object, object], actual: dict[object, object]) -> bool:
    return expected.keys() == actual.keys() and all(json_equal(value, actual[key]) for key, value in expected.items())


def _json_list_equal(expected: list[object], actual: list[object]) -> bool:
    return len(expected) == len(actual) and all(
        json_equal(left, right) for left, right in zip(expected, actual, strict=True)
    )


def _bounded_scalar_failure(
    value: object,
    current_pointer: str,
    budget: RelationBudget,
) -> RealizationRelationResult | None:
    failure = None
    if exhausted := budget.spend_scalar(value):
        failure = relation_result(
            RealizationRelationStatus.INVALID
            if exhausted == "invalid_utf8"
            else RealizationRelationStatus.LIMIT_EXCEEDED,
            current_pointer,
            f"Realization value validation exceeded {exhausted}.",
        )
    elif isinstance(value, float) and not math.isfinite(value):
        failure = relation_result(
            RealizationRelationStatus.INVALID,
            current_pointer,
            "Realization values must use finite JSON numbers.",
        )
    elif type(value) is int and value.bit_length() > budget.limits.max_scalar_bytes * 8:
        failure = relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            current_pointer,
            "Realization value validation exceeded the integer-size limit.",
        )
    elif type(value) not in (str, int, float, bool, type(None), dict, list) and not (
        budget.python_carriers and isinstance(value, tuple)
    ):
        failure = relation_result(
            RealizationRelationStatus.INVALID,
            current_pointer,
            "Realization value is not JSON-compatible.",
        )
    return failure


def _bounded_container_failure(
    value: dict[object, object] | list[object] | tuple[object, ...],
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> RealizationRelationResult | None:
    current_pointer = pointer(path)
    failure = None
    if len(value) > budget.limits.max_members:
        failure = relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            current_pointer,
            "Realization value validation exceeded max_members.",
        )
    else:
        children = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in children:
            if isinstance(value, dict) and not isinstance(key, str):
                failure = relation_result(
                    RealizationRelationStatus.INVALID,
                    current_pointer,
                    "Realization record keys must be strings.",
                )
            else:
                if isinstance(value, dict):
                    failure = _bounded_scalar_failure(key, current_pointer, budget)
                if failure is None:
                    failure = validate_bounded_value(child, (*path, str(key)), depth + 1, budget)
            if failure is not None:
                break
    return failure


def validate_bounded_value(
    value: object,
    path: tuple[str, ...],
    depth: int,
    budget: RelationBudget,
) -> RealizationRelationResult | None:
    current_pointer = pointer(path)
    failure = None
    if budget.python_carriers and isinstance(value, Enum):
        value = value.value
    if exhausted := budget.spend_node(depth):
        failure = relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            current_pointer,
            f"Realization value validation exceeded {exhausted}.",
        )
    if failure is None and budget.python_carriers:
        value, failure = _python_record_values(value, current_pointer, budget)
    if failure is None:
        failure = _bounded_scalar_failure(value, current_pointer, budget)
    if failure is None and (isinstance(value, (dict, list)) or budget.python_carriers and isinstance(value, tuple)):
        failure = _bounded_container_failure(value, path, depth, budget)
    return failure


def _python_record_values(
    value: object, current_pointer: str, budget: RelationBudget
) -> tuple[object, RealizationRelationResult | None]:
    """Visit DTO fields without invoking serialization or recursively copying."""

    if isinstance(value, BaseModel):
        names = type(value).model_fields
        extra = value.model_extra or {}
    elif is_dataclass(value) and not isinstance(value, type):
        names = tuple(field.name for field in fields(value))
        extra = {}
    else:
        return value, None
    if len(names) + len(extra) > budget.limits.max_members:
        return value, relation_result(
            RealizationRelationStatus.LIMIT_EXCEEDED,
            current_pointer,
            "Realization value validation exceeded max_members.",
        )
    return {**{name: getattr(value, name) for name in names}, **extra}, None


def validate_realization_value(
    value: object,
    *,
    limits: RealizationConstraintLimits = DEFAULT_REALIZATION_CONSTRAINT_LIMITS,
    python_carriers: bool = False,
) -> RealizationRelationResult:
    """Admit a finite JSON value before copying, projecting or comparing it.

    This uses the evaluator's existing value admission without creating a
    constraint tree or treating shape validity as realization permission.
    Internal runtime DTOs may opt into dataclass/model/tuple/enum carriers that
    their existing portable codecs serialize as JSON objects/arrays/scalars. The relation itself stays
    strict JSON; this option does not change equality or conformance.
    """

    failure = validate_bounded_value(value, (), 0, RelationBudget(limits, python_carriers=python_carriers))
    return failure if failure is not None else RealizationRelationResult(RealizationRelationStatus.CONFORMANT)

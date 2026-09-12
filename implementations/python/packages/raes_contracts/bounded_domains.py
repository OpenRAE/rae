"""Dependency-neutral bounded value-domain algebra.

These closed descriptors are shared by SDL scenario families and ADR-070
realization envelopes.  They describe value sets only; selection policy,
backend posture, and witness generation remain outside this module.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from raes_contracts._base import ContractModel, NonEmptyString

__all__ = [
    "BooleanDomain",
    "DomainDescriptor",
    "DomainScalar",
    "EnumDomain",
    "ExactDomain",
    "GovernedReferenceDomain",
    "NumericIntervalDomain",
    "NumericType",
    "NullDomain",
    "NullableDomainDescriptor",
    "RecordDomain",
    "scalar_in_domain",
    "scalar_matches_numeric_type",
]

DomainScalar = bool | int | float | str


class NumericType(str, Enum):
    """Declared numeric type for a numeric-interval domain."""

    INTEGER = "integer"
    NUMBER = "number"


class ExactDomain(ContractModel):
    """A singleton value set: values equal to ``value``."""

    kind: Literal["exact"] = "exact"
    value: DomainScalar


class EnumDomain(ContractModel):
    """A finite value set: values equal to one listed member."""

    kind: Literal["enum"] = "enum"
    values: list[DomainScalar] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique(self) -> EnumDomain:
        seen: set[tuple[str, object]] = set()
        for member in self.values:
            key = (type(member).__name__, member)
            if key in seen:
                raise ValueError("enum domain values must be unique")
            seen.add(key)
        return self


class BooleanDomain(ContractModel):
    """Booleans: both ``true``/``false``, or an exact boolean when ``value`` set."""

    kind: Literal["boolean"] = "boolean"
    value: bool | None = None


class NullDomain(ContractModel):
    """The singleton JSON-null domain, distinct from omission or unknown."""

    kind: Literal["null"] = "null"


class NumericIntervalDomain(ContractModel):
    """Numbers of ``numeric_type`` inside a bounded interval.

    Both endpoints are required (the fragment admits only *bounded* intervals,
    ``envelope-semantics.md`` R3). An integer interval requires integral
    endpoints. Empty intervals are rejected at construction.
    """

    kind: Literal["numeric-interval"] = "numeric-interval"
    numeric_type: NumericType
    lower: float
    upper: float
    lower_closed: bool = True
    upper_closed: bool = True

    @model_validator(mode="after")
    def _validate_interval(self) -> NumericIntervalDomain:
        if self.numeric_type is NumericType.INTEGER:
            if self.lower != int(self.lower) or self.upper != int(self.upper):
                raise ValueError("integer numeric-interval endpoints must be integral")
        if self.lower > self.upper:
            raise ValueError("numeric-interval lower endpoint must not exceed upper")
        if self.lower == self.upper and not (self.lower_closed and self.upper_closed):
            raise ValueError("degenerate numeric-interval must be closed on both endpoints")
        return self


class GovernedReferenceDomain(ContractModel):
    """References in a finite governed set under a named authority."""

    kind: Literal["governed-reference"] = "governed-reference"
    authority: NonEmptyString
    allowed_refs: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique(self) -> GovernedReferenceDomain:
        if len(self.allowed_refs) != len(set(self.allowed_refs)):
            raise ValueError("governed-reference allowed_refs must be unique")
        return self


class RecordDomain(ContractModel):
    """Product structure: each declared field references another named domain.

    ``extra`` controls undeclared fields: ``False`` (closed) rejects any field not
    named in ``fields``; ``True`` (open) admits them. Field values reference domain
    names resolved against the envelope's ``domains`` map, keeping the structure
    acyclic and free of inline recursion.
    """

    kind: Literal["record"] = "record"
    fields: dict[NonEmptyString, NonEmptyString] = Field(min_length=1)
    extra: bool = False


DomainDescriptor = Annotated[
    ExactDomain | EnumDomain | BooleanDomain | NumericIntervalDomain | GovernedReferenceDomain | RecordDomain,
    Field(discriminator="kind"),
]

NullableDomainDescriptor = Annotated[
    ExactDomain
    | EnumDomain
    | BooleanDomain
    | NullDomain
    | NumericIntervalDomain
    | GovernedReferenceDomain
    | RecordDomain,
    Field(discriminator="kind"),
]


def scalar_matches_numeric_type(value: object, numeric_type: NumericType) -> bool:
    """Return whether a value is a non-Boolean number of the declared type."""

    if isinstance(value, bool):
        return False
    if numeric_type is NumericType.INTEGER:
        return isinstance(value, int)
    return isinstance(value, (int, float))


def _scalar_eq(value: object, member: DomainScalar) -> bool:
    return type(value) is type(member) and value == member


def _interval_member(value: object, descriptor: NumericIntervalDomain) -> bool:
    if not scalar_matches_numeric_type(value, descriptor.numeric_type):
        return False
    numeric = float(value)
    lower_ok = numeric >= descriptor.lower if descriptor.lower_closed else numeric > descriptor.lower
    upper_ok = numeric <= descriptor.upper if descriptor.upper_closed else numeric < descriptor.upper
    return lower_ok and upper_ok


_SCALAR_MEMBER_CHECKS: dict[type, Callable[..., bool]] = {
    ExactDomain: lambda value, descriptor: _scalar_eq(value, descriptor.value),
    EnumDomain: lambda value, descriptor: any(_scalar_eq(value, member) for member in descriptor.values),
    BooleanDomain: lambda value, descriptor: (
        isinstance(value, bool) and (descriptor.value is None or value == descriptor.value)
    ),
    NullDomain: lambda value, _descriptor: value is None,
    NumericIntervalDomain: _interval_member,
    GovernedReferenceDomain: lambda value, descriptor: isinstance(value, str) and value in descriptor.allowed_refs,
}


def scalar_in_domain(value: object, descriptor: DomainDescriptor) -> bool:
    """Return scalar membership; record products are handled by their owner."""

    check = _SCALAR_MEMBER_CHECKS.get(type(descriptor))
    return check(value, descriptor) if check is not None else False

"""SEM-218 typed authoring surface and scoped realization cascade."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from raes_contracts.bounded_domains import DomainDescriptor
from raes_contracts.compute_substrate import validate_compute_substrate_constraint
from raes_contracts.identifiers import PortableIdentifier
from raes_contracts.json_pointer import array_index, pointer_tokens
from raes_contracts.sdl_model import SDLModel
from raes_contracts.vocabulary import Closure

_JSON_POINTER_PATTERN = r"^(?:/(?:[^~/]|~[01])*)*$"
_JSON_POINTER_RE = re.compile(_JSON_POINTER_PATTERN)


class AuthorRealizationPosture(str, Enum):
    """Authored default posture, distinct from capability support modes."""

    CLOSED = "closed"
    OPEN = "open"
    UNSPECIFIED = "unspecified"


class ComputeRealizationConcern(str, Enum):
    """Portable compute concerns whose mechanisms remain backend-selected."""

    COMPUTE_SUBSTRATE = "compute-substrate"


class RealizationConstraintPosture(str, Enum):
    """Exact, finite-constrained, or delegated author mechanism intent."""

    OPEN = "open"
    CONSTRAINED = "constrained"
    EXACT = "exact"


class RealizationConstraintDesignation(SDLModel):
    """One addressed author constraint over a governed realization concern."""

    namespace: tuple[PortableIdentifier, ...] = Field(default=(), max_length=31)
    field_pointer: str = Field(min_length=1, max_length=4096, pattern=_JSON_POINTER_PATTERN)
    concern: ComputeRealizationConcern
    posture: RealizationConstraintPosture
    domain: DomainDescriptor | None = None
    provenance: Literal["author-declared", "legacy-node-type-vm"] = Field(
        default="author-declared",
        exclude=True,
        json_schema_extra={"x-raes-internal-provenance": True},
    )

    @model_validator(mode="after")
    def _validate_constraint(self) -> RealizationConstraintDesignation:
        if _JSON_POINTER_RE.fullmatch(self.field_pointer) is None:
            raise ValueError("field_pointer must be a canonical RFC 6901 JSON Pointer")
        validate_compute_substrate_constraint(self.posture, self.domain)
        return self


class RealizationScopeDesignation(SDLModel):
    """One typed lexical override at a canonical composed-model scope."""

    namespace: tuple[PortableIdentifier, ...] = Field(default=(), max_length=31)
    field_pointer: str = Field(min_length=1, max_length=4096, pattern=_JSON_POINTER_PATTERN)
    posture: AuthorRealizationPosture

    @model_validator(mode="after")
    def _validate_pointer(self) -> RealizationScopeDesignation:
        if _JSON_POINTER_RE.fullmatch(self.field_pointer) is None:
            raise ValueError("field_pointer must be a canonical RFC 6901 JSON Pointer")
        return self


class RealizationDesignation(SDLModel):
    """Scenario-root SEM-218 designation table."""

    default: AuthorRealizationPosture = AuthorRealizationPosture.UNSPECIFIED
    scopes: tuple[RealizationScopeDesignation, ...] = ()
    constraints: tuple[RealizationConstraintDesignation, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_scopes(self) -> RealizationDesignation:
        identities = [(entry.namespace, entry.field_pointer) for entry in self.scopes]
        if len(identities) != len(set(identities)):
            raise ValueError("realization scopes must have unique namespace and field_pointer identities")
        constraint_identities = [(entry.namespace, entry.field_pointer, entry.concern) for entry in self.constraints]
        if len(constraint_identities) != len(set(constraint_identities)):
            raise ValueError(
                "realization constraints must have unique namespace, field_pointer, and concern identities"
            )
        return self


class RealizationDesignationRecord(SDLModel):
    """Portable authored designation carried across SDL document phases."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    namespace: tuple[PortableIdentifier, ...] = Field(default=(), max_length=31)
    field_pointer: str = Field(default="", max_length=4096, pattern=_JSON_POINTER_PATTERN)
    posture: AuthorRealizationPosture

    @model_validator(mode="after")
    def _validate_pointer(self) -> RealizationDesignationRecord:
        if _JSON_POINTER_RE.fullmatch(self.field_pointer) is None:
            raise ValueError("field_pointer must be an RFC 6901 JSON Pointer")
        return self

    @property
    def scope_reference(self) -> str:
        namespace = ".".join(self.namespace)
        pointer = self.field_pointer or "/"
        return f"{namespace}#{pointer}"


class RealizationConstraintRecord(SDLModel):
    """Portable addressed author constraint carried across SDL phases."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    namespace: tuple[PortableIdentifier, ...] = Field(default=(), max_length=31)
    field_pointer: str = Field(min_length=1, max_length=4096, pattern=_JSON_POINTER_PATTERN)
    concern: ComputeRealizationConcern
    posture: RealizationConstraintPosture
    domain: DomainDescriptor | None = None
    provenance: Literal["author-declared", "legacy-node-type-vm"] = "author-declared"

    @model_validator(mode="after")
    def _validate_constraint(self) -> RealizationConstraintRecord:
        validate_compute_substrate_constraint(self.posture, self.domain)
        return self

    @property
    def governing_scope(self) -> str:
        namespace = ".".join(self.namespace)
        return f"{namespace}#{self.field_pointer}"


@dataclass(frozen=True)
class RealizationResolution:
    """Effective closure and its non-value-bearing governing source."""

    closure: Closure | None
    governing_scope: str | None
    delegated: bool
    source: str


ApparatusDefaultResolver = Callable[[str, tuple[str, ...]], Closure]


def designation_records(
    designation: RealizationDesignation,
    *,
    namespace: tuple[str, ...] = (),
) -> tuple[RealizationDesignationRecord, ...]:
    """Lower one authoring surface into portable declaration records."""

    records = [
        RealizationDesignationRecord(
            namespace=namespace,
            field_pointer="",
            posture=designation.default,
        )
    ]
    records.extend(
        RealizationDesignationRecord(
            namespace=(*namespace, *entry.namespace),
            field_pointer=entry.field_pointer,
            posture=entry.posture,
        )
        for entry in designation.scopes
    )
    return tuple(records)


def constraint_records(
    designation: RealizationDesignation,
    *,
    namespace: tuple[str, ...] = (),
) -> tuple[RealizationConstraintRecord, ...]:
    """Lower author constraints into portable phase-provenance records."""

    return tuple(
        RealizationConstraintRecord(
            namespace=(*namespace, *entry.namespace),
            field_pointer=entry.field_pointer,
            concern=entry.concern,
            posture=entry.posture,
            domain=entry.domain,
            provenance=entry.provenance,
        )
        for entry in designation.constraints
    )


def resolve_realization_designation(
    records: Iterable[RealizationDesignationRecord],
    *,
    field_pointer: str,
    owner_namespace: tuple[str, ...] = (),
    apparatus_default: ApparatusDefaultResolver | None = None,
) -> RealizationResolution:
    """Resolve the deterministic most-specific concrete lexical posture."""

    if _JSON_POINTER_RE.fullmatch(field_pointer) is None:
        raise ValueError("field_pointer must be an RFC 6901 JSON Pointer")
    applicable = tuple(
        record
        for record in records
        if _namespace_contains(record.namespace, owner_namespace)
        and _pointer_contains(record.field_pointer, field_pointer)
    )
    concrete = tuple(record for record in applicable if record.posture is not AuthorRealizationPosture.UNSPECIFIED)
    if concrete:
        governing = max(concrete, key=_specificity)
        closure = Closure.OPEN_WORLD if governing.posture is AuthorRealizationPosture.OPEN else Closure.CLOSED_WORLD
        return RealizationResolution(closure, governing.scope_reference, False, "scope")
    if applicable:
        governing = max(applicable, key=_specificity)
        resolver = apparatus_default or _closed_apparatus_default
        return RealizationResolution(
            resolver(field_pointer, owner_namespace),
            governing.scope_reference,
            True,
            "apparatus-default",
        )
    return RealizationResolution(Closure.CLOSED_WORLD, None, False, "legacy-default")


def resolve_json_pointer_surface(root: object, pointer: str) -> tuple[bool, object]:
    """Resolve a strict RFC 6901 pointer against a typed SDL surface."""

    if _JSON_POINTER_RE.fullmatch(pointer) is None:
        return False, None
    current = root
    for segment in pointer_tokens(pointer):
        if isinstance(current, BaseModel) and segment in type(current).model_fields:
            current = getattr(current, segment)
        elif isinstance(current, Mapping) and segment in current:
            current = current[segment]
        elif (
            isinstance(current, Sequence)
            and not isinstance(current, (str, bytes, bytearray))
            and (index := array_index(segment, len(current))) is not None
        ):
            current = current[index]
        else:
            return False, None
    return True, current


def _closed_apparatus_default(_field_pointer: str, _owner_namespace: tuple[str, ...]) -> Closure:
    return Closure.CLOSED_WORLD


def _namespace_contains(scope: tuple[str, ...], owner: tuple[str, ...]) -> bool:
    return len(scope) <= len(owner) and owner[: len(scope)] == scope


def _pointer_segments(pointer: str) -> tuple[str, ...]:
    return tuple(pointer.split("/")[1:])


def _pointer_contains(scope: str, field_pointer: str) -> bool:
    scope_segments = _pointer_segments(scope)
    field_segments = _pointer_segments(field_pointer)
    return len(scope_segments) <= len(field_segments) and field_segments[: len(scope_segments)] == scope_segments


def _specificity(record: RealizationDesignationRecord) -> tuple[int, int, str, str]:
    return (
        len(_pointer_segments(record.field_pointer)),
        len(record.namespace),
        ".".join(record.namespace),
        record.field_pointer,
    )


__all__ = [
    "ApparatusDefaultResolver",
    "AuthorRealizationPosture",
    "ComputeRealizationConcern",
    "RealizationDesignation",
    "RealizationDesignationRecord",
    "RealizationConstraintDesignation",
    "RealizationConstraintPosture",
    "RealizationConstraintRecord",
    "RealizationResolution",
    "RealizationScopeDesignation",
    "designation_records",
    "constraint_records",
    "resolve_json_pointer_surface",
    "resolve_realization_designation",
]

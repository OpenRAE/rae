"""Pure, bounded version predicates under exact installed semantic identities.

Unrecognized semantic coordinates remain exchangeable and evaluate unsupported.
No profile value selects imports, commands, remote resolution or host inspection.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from univers.debian import compare_versions
from univers.rpm import compare_rpm_versions

from ._base import ContractModel
from ._domain_profile_contracts import DomainProfileSemanticContractModel
from .canonical import canonical_json_digest

if TYPE_CHECKING:
    from .realization_structure import RealizationConstraintDocument

_AUTHORITY = "https://openrae.org/semantics/versions"
_TRIPLET = re.compile(r"(?:0|[1-9]\d{0,8})(?:\.(?:0|[1-9]\d{0,8})){2}\Z", re.ASCII)
_DEBIAN = re.compile(r"(?:\d+:)?\d[A-Za-z0-9.+~]*(?:-[A-Za-z0-9.+~\-]*[A-Za-z0-9.+~])?\Z", re.ASCII)
_RPM = re.compile(r"(?:\d+:)?[A-Za-z0-9][A-Za-z0-9.+_~^]*(?:-[A-Za-z0-9.+_~^]+)?\Z", re.ASCII)
VersionMembership = Literal["conformant", "nonconformant", "unresolved", "unsupported"]


def version_relation(name: str) -> DomainProfileSemanticContractModel:
    """Return the exact public identity of an installed relation revision."""

    if name not in _COMPARATORS:
        raise ValueError("Unsupported installed version relation")
    return DomainProfileSemanticContractModel(
        authority=_AUTHORITY,
        contract_id=name,
        revision="1",
        digest=canonical_json_digest({"relation": name, "revision": "1"}),
    )


def _triplet_compare(left: str, right: str) -> int:
    first = tuple(map(int, left.split(".")))
    second = tuple(map(int, right.split(".")))
    return (first > second) - (first < second)


# Fixed installed code, never a mutable registration or profile-data callback.
_COMPARATORS = MappingProxyType(
    {
        "numeric-triplet": (_TRIPLET, _triplet_compare),
        "debian": (_DEBIAN, compare_versions),
        "rpm": (_RPM, compare_rpm_versions),
    }
)


def _comparator(relation: DomainProfileSemanticContractModel) -> tuple[re.Pattern[str], Callable] | None:
    entry = _COMPARATORS.get(relation.contract_id)
    return entry if entry is not None and relation == version_relation(relation.contract_id) else None


class VersionDomain(ContractModel):
    """An optional one-sided or bounded restriction; exact SDL strings stay exact.

    Comparison equality is relation-owned. This never asserts correspondence
    between an application version and a distribution package version.
    """

    kind: Literal["version"] = "version"
    relation: DomainProfileSemanticContractModel
    lower: str | None = Field(default=None, min_length=1, max_length=256)
    upper: str | None = Field(default=None, min_length=1, max_length=256)
    lower_closed: bool = True
    upper_closed: bool = True

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        schema["anyOf"] = [
            {"required": [field], "properties": {field: {"type": "string"}}} for field in ("lower", "upper")
        ]
        return schema

    @model_validator(mode="after")
    def validate_bounds(self) -> VersionDomain:
        if self.lower is None and self.upper is None:
            raise ValueError("Unrestricted version requires no version constraint")
        entry = _comparator(self.relation)
        if entry is not None:
            pattern, compare = entry
            if any(value is not None and pattern.fullmatch(value) is None for value in (self.lower, self.upper)):
                raise ValueError("Version constraint endpoint is incomparable under its relation")
            if self.lower is not None and self.upper is not None:
                ordering = compare(self.lower, self.upper)
                if not _satisfies_bound(-ordering, self.lower_closed and self.upper_closed):
                    raise ValueError("Version constraint has an empty interval")
        return self


def _satisfies_bound(ordering: int, closed: bool) -> bool:
    """Admit a point above a lower bound (or below a reversed upper bound)."""
    return ordering > 0 or ordering == 0 and closed


def _within_bounds(value: str, domain: VersionDomain, compare: Callable) -> bool:
    lower = 1 if domain.lower is None else compare(value, domain.lower)
    upper = -1 if domain.upper is None else compare(value, domain.upper)
    return _satisfies_bound(lower, domain.lower_closed) and _satisfies_bound(-upper, domain.upper_closed)


def version_membership(value: object, domain: VersionDomain) -> VersionMembership:
    """Evaluate one bounded version without converting unknown support to false."""

    entry = _comparator(domain.relation)
    if entry is None:
        return "unsupported"
    pattern, compare = entry
    if not isinstance(value, str) or len(value) > 256 or pattern.fullmatch(value) is None:
        return "unresolved"
    admitted = _within_bounds(value, domain, compare)
    return "conformant" if admitted else "nonconformant"


def _version_domains(document: RealizationConstraintDocument) -> Iterator[VersionDomain]:
    """Visit an already bounded, admitted recursive document once."""
    pending = [document.root, *document.definitions.values()]
    while pending:
        node = pending.pop()
        if node.kind == "domain" and isinstance(node.domain, VersionDomain):
            yield node.domain
        if node.kind == "recursive-record":
            pending.extend(node.fields.values())
        elif node.kind == "keyed-collection":
            pending.extend(member.constraint for member in node.members)
        elif node.kind == "sequence":
            pending.extend(node.items)
        elif node.kind == "all-of":
            pending.extend(node.constraints)


def version_relations_supported(document: RealizationConstraintDocument) -> bool:
    """Inspect a validated recursive document for unsupported version predicates."""
    return all(_comparator(domain.relation) is not None for domain in _version_domains(document))


def has_version_constraints(document: RealizationConstraintDocument) -> bool:
    """Whether a concern requires comparison rather than exact-only support."""
    return next(_version_domains(document), None) is not None


__all__ = [
    "VersionDomain",
    "VersionMembership",
    "has_version_constraints",
    "version_membership",
    "version_relation",
    "version_relations_supported",
]

"""Shared value types for authored identity-domain topology analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


class DomainNodeRole(str, Enum):
    """A node's authored role within an identity domain."""

    CONTROLLER = "controller"
    MEMBER = "member"


@dataclass(frozen=True)
class DomainTopologyIssue:
    """Machine-readable authored-topology consistency issue.

    ``owner`` is the ``(section, name)`` pair of the declaration that the message names first.
    """

    code: str
    message: str
    owner: tuple[str, str] | None = None


@dataclass(frozen=True)
class DomainNodeBinding:
    """Normalized name-level binding for one domain-participating node."""

    node_name: str
    domain_name: str
    role: DomainNodeRole
    controller_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainAccountBinding:
    """Normalized name-level binding for one domain-scoped account."""

    account_name: str
    node_name: str
    domain_name: str


@dataclass(frozen=True)
class DomainTopologyAnalysis:
    """Normalized topology facts and fail-closed authoring issues."""

    node_bindings: Mapping[str, DomainNodeBinding] = field(default_factory=dict)
    account_bindings: Mapping[str, DomainAccountBinding] = field(default_factory=dict)
    controllers_by_domain: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    issues: tuple[DomainTopologyIssue, ...] = ()

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)


def resolve_section_ref(ref: object, section: str, declarations: Mapping[str, object]) -> str | None:
    """Resolve a local or section-qualified authored reference."""

    if not isinstance(ref, str):
        return None
    if ref in declarations:
        return ref
    prefix = f"{section}."
    qualified = ref[len(prefix) :] if ref.startswith(prefix) else ""
    return qualified if qualified in declarations else None


def topology_issue(code: str, message: str, owner: tuple[str, str]) -> DomainTopologyIssue:
    """Build a normalized authored-topology issue of the *owner* declaration."""

    return DomainTopologyIssue(code=code, message=message, owner=owner)


__all__ = [
    "DomainAccountBinding",
    "DomainNodeBinding",
    "DomainNodeRole",
    "DomainTopologyAnalysis",
    "DomainTopologyIssue",
    "resolve_section_ref",
    "topology_issue",
]

"""Normalized reference, issue, dependency, and analysis records for objective semantics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from ..assessment import AssessmentResourceKind
from ..objectives import (
    ObjectiveDependencyRole,
    ObjectiveWindowAnalysis,
    ObjectiveWindowReferenceKind,
)


class ObjectiveReferenceKind(str, Enum):
    """Kinds of cross-resource reference an objective carries."""

    OWNER = "owner"
    ASSIGNMENT = "assignment"
    ACTION_CONSTRAINT = "action_constraint"
    TARGET = "target"
    SUCCESS = "success"
    WINDOW = "window"
    DEPENDENCY = "dependency"


@dataclass(frozen=True)
class ObjectiveReference:
    """A normalized reference from one objective to an upstream resource."""

    raw: str
    canonical_name: str
    reference_kind: ObjectiveReferenceKind
    source_name: str
    dependency_roles: tuple[ObjectiveDependencyRole, ...] = ()
    #: Set on ``SUCCESS`` references to preserve the assertion namespace.
    success_resource_kind: AssessmentResourceKind | None = None
    window_reference_kind: ObjectiveWindowReferenceKind | None = None
    workflow_name: str | None = None
    step_name: str | None = None
    #: Reserved for later module/import expansion; the analysis runs on
    #: already-composed scenarios, so it is empty today.
    namespace_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObjectiveIssue:
    """A machine-readable objective-semantics consistency problem.

    ``ref`` names the offending reference target. ``actor_name`` carries the
    declaring agent for ``action-not-declared``. ``candidates`` carries the
    sorted alternatives for an ambiguous target. ``workflow_name`` / ``step_name``
    carry the parsed parts of a window step ref. ``objective_name`` is empty for
    the global ``objective.dependency-cycle`` issue.
    """

    code: str
    objective_name: str
    ref: str | None = None
    actor_name: str | None = None
    candidates: tuple[str, ...] = ()
    workflow_name: str | None = None
    step_name: str | None = None


@dataclass(frozen=True)
class ObjectiveResourceDependencies:
    """Derived upstream dependencies for one objective."""

    name: str
    ordering_names: tuple[str, ...] = ()
    refresh_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObjectiveSemanticAnalysis:
    """Result of analyzing the declarative objectives of a scenario."""

    references: tuple[ObjectiveReference, ...] = ()
    issues: tuple[ObjectiveIssue, ...] = ()
    dependencies: tuple[ObjectiveResourceDependencies, ...] = ()
    window_analyses: Mapping[str, ObjectiveWindowAnalysis] = field(default_factory=dict)

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    def issues_of_code(self, code: str) -> tuple[ObjectiveIssue, ...]:
        return tuple(issue for issue in self.issues if issue.code == code)

    def references_of_kind(self, kind: ObjectiveReferenceKind) -> tuple[ObjectiveReference, ...]:
        return tuple(ref for ref in self.references if ref.reference_kind == kind)

    def dependencies_for(self, name: str) -> ObjectiveResourceDependencies:
        for dependency in self.dependencies:
            if dependency.name == name:
                return dependency
        raise KeyError(name)


@dataclass(frozen=True)
class AssessmentResourceCatalog:
    """The backend-neutral assertion section objective success may name."""

    assertions: Mapping[str, object]


@dataclass(frozen=True)
class WindowResourceCatalog:
    """The four timeline section maps an objective's window may name."""

    stories: Mapping[str, object]
    scripts: Mapping[str, object]
    events: Mapping[str, object]
    workflows: Mapping[str, object]

"""Shared model objects for GitHub Actions job and use-site validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from tools.tooling_artifact_policy_conditions import UNTRUSTED_TRUST_CLASSES
from tools.tooling_artifact_policy_use_effects import ActionResources


@dataclass(frozen=True)
class ActionPolicyIndex:
    """Everything one workflow job is validated against."""

    policy: Mapping[str, Any]
    source_identities: Mapping[tuple[str, str], tuple[str, Mapping[str, Any]]]
    resources: ActionResources
    profile_ids: set[str]
    protected_refs: set[str]


@dataclass
class ObservedUse:
    """The workflow jobs, use sites, and action sources actually observed."""

    jobs: set[tuple[str, str]] = field(default_factory=set)
    sites: set[tuple[str, str, str]] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)


@dataclass
class ActionValidation:
    """Shared policy index, declarations, and observations for one validation run."""

    index: ActionPolicyIndex
    declared_jobs: Mapping[tuple[object, object], Mapping[str, Any]]
    declared_sites: Mapping[tuple[object, object, object], Mapping[str, Any]]
    observed: ObservedUse = field(default_factory=ObservedUse)


@dataclass(frozen=True)
class JobSite:
    """One concrete workflow job under validation."""

    path: str
    workflow: Mapping[str, Any]
    job_name: str
    job: Mapping[str, Any]
    trust_seed: set[str]


@dataclass
class JobFacts:
    """The capabilities one workflow job actually has."""

    trust_classes: set[str]
    permissions: dict[str, str]
    runner: str
    runner_contexts: list[tuple[str, dict[str, object]]]
    credentials: set[str]
    ambient_credentials: set[str]
    host_profiles: set[str]

    @property
    def untrusted(self) -> bool:
        """Report whether any untrusted trust class reaches this job."""

        return bool(self.trust_classes & UNTRUSTED_TRUST_CLASSES)

    @property
    def write_permissions(self) -> set[str]:
        """Name every scope this job holds at write level."""

        return {name for name, level in self.permissions.items() if level == "write"}


@dataclass(frozen=True)
class StepContext:
    """One workflow step and the trust it runs under."""

    step: Mapping[str, Any]
    trust_classes: set[str]
    untrusted: bool


@dataclass(frozen=True)
class StepUse:
    """One observed action use and the effects it is credited with."""

    declared: Mapping[str, Any]
    source_id: str
    action: str
    commit: str
    inputs: dict[str, object]
    trust_classes: set[str]
    cache_role: str
    artifact_role: str
    allowed_origins: set[str]


@dataclass
class JobSteps:
    """The aggregate effects of every step in one job."""

    uses: list[StepUse] = field(default_factory=list)
    cache_roles: set[str] = field(default_factory=lambda: {"none"})
    artifact_roles: set[str] = field(default_factory=lambda: {"none"})
    origins: set[str] = field(default_factory=set)
    untrusted_credentials: set[str] = field(default_factory=set)


__all__ = (
    "ActionPolicyIndex",
    "ActionValidation",
    "JobFacts",
    "JobSite",
    "JobSteps",
    "ObservedUse",
    "StepContext",
    "StepUse",
)

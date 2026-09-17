"""Process identity + Linux capability policy models for SDL runtime nodes.

This module owns the schemas that ADR-030 places under
``Node.runtime.linux_capabilities``: the observed process identity used
both as a process inventory entry *and* as a selector for a scoped
capability override, plus the container-wide capability baseline and the
process-/subtree-scoped capability deltas that ride on top of it.

It is split out of ``runtime_configuration`` so the file housing the
top-level ``RuntimeConfiguration`` aggregate stays under the per-file size
cap from ADR-015. ``RuntimeConfiguration`` re-imports
``RuntimeProcessIdentity`` and ``RuntimeCapabilityPolicy`` from here so
external callers still reach them via ``raes.nodes``.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import Field, field_validator, model_validator

from raes.runtime_vocabulary import GovernedVocabulary

from ._base import (
    SDLModel,
    is_variable_ref,
    parse_bool_or_var,
    parse_int_or_var,
)
from .runtime_values import (
    absolute_path_or_var as _absolute_path_or_var,
)
from .runtime_values import (
    coerce_string_list as _coerce_string_list,
)
from .runtime_values import (
    parse_runtime_enum_or_var as _parse_runtime_enum_or_var,
)

__all__ = [
    "RuntimeCapabilityOverrideScope",
    "RuntimeCapabilityPolicy",
    "RuntimeProcessCapabilityOverride",
    "RuntimeProcessIdentity",
    "RuntimeProcessRole",
]


class RuntimeProcessRole(str, Enum):
    """Observed role of a process in a runtime process set."""

    PRIMARY = "primary"
    SUPERVISOR = "supervisor"
    WORKER = "worker"
    SIDECAR = "sidecar"
    AGENT = "agent"
    OTHER = "other"
    UNKNOWN = "unknown"


class RuntimeCapabilityOverrideScope(str, Enum):
    """Scope of a ``RuntimeProcessCapabilityOverride``.

    ``PROCESS`` records a capability delta that applies only to the subject
    process itself; ``SUBTREE`` records a delta that applies to the subject
    process and every descendant it spawns (the motivating case is
    ``capsh --drop=cap_audit_control`` exec'ing ``sshd``, after which the
    interactive shell subtree runs without ``CAP_AUDIT_CONTROL``).
    """

    PROCESS = "process"
    SUBTREE = "subtree"


def _normalize_capability_name(value: str) -> str:
    if is_variable_ref(value):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("capability names must be non-empty strings")
    normalized = value.strip().upper().replace("-", "_")
    if not re.fullmatch(r"CAP_[A-Z0-9_]+", normalized):
        raise ValueError("capability names must use Linux CAP_* form")
    return normalized


class RuntimeProcessIdentity(SDLModel):
    """Observed process identity for a runtime node."""

    name: str = ""
    pid: int | str | None = None
    parent_pid: int | str | None = None
    command: list[str] = Field(default_factory=list)
    command_redacted: bool | str = False
    role: GovernedVocabulary[RuntimeProcessRole] = RuntimeProcessRole.OTHER
    user: str = ""
    group: str = ""
    working_directory: str = ""
    description: str = ""

    @field_validator("pid", mode="before")
    @classmethod
    def parse_pid(cls, v: int | str | None) -> int | str | None:
        return parse_int_or_var(v, minimum=1, field_name="pid") if v is not None else v

    @field_validator("parent_pid", mode="before")
    @classmethod
    def parse_parent_pid(cls, v: int | str | None) -> int | str | None:
        return parse_int_or_var(v, minimum=1, field_name="parent_pid") if v is not None else v

    @field_validator("command", mode="before")
    @classmethod
    def normalize_command(cls, v: str | list[str] | None) -> list[str]:
        return _coerce_string_list(v)

    @field_validator("command_redacted", mode="before")
    @classmethod
    def parse_command_redacted(cls, v: bool | str) -> bool | str:
        return parse_bool_or_var(v, field_name="command_redacted")

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, v: RuntimeProcessRole | str) -> RuntimeProcessRole | str:
        return _parse_runtime_enum_or_var(v, RuntimeProcessRole, field_name="role")

    @field_validator("working_directory")
    @classmethod
    def validate_working_directory(cls, v: str) -> str:
        return _absolute_path_or_var(v, field_name="working_directory") if v else v


class RuntimeProcessCapabilityOverride(SDLModel):
    """A capability delta scoped to a single process or its descendant subtree.

    Per ADR-030, scoped Linux-capability facts stay under
    ``RuntimeCapabilityPolicy`` rather than migrating onto
    ``RuntimeProcessIdentity``. ``subject`` reuses the existing process
    identity model as a selector / evidence anchor — it identifies *which*
    process or subtree the delta applies to but does not own capability
    semantics. ``effective`` / ``add`` / ``drop`` record the scoped delta
    relative to the container-wide baseline on the enclosing
    ``RuntimeCapabilityPolicy``; ``required`` is intentionally omitted from
    this surface because overrides describe deltas, not new container-wide
    requirements.
    """

    subject: RuntimeProcessIdentity
    scope: GovernedVocabulary[RuntimeCapabilityOverrideScope] = RuntimeCapabilityOverrideScope.PROCESS
    effective: list[str] = Field(default_factory=list)
    add: list[str] = Field(default_factory=list)
    drop: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("scope", mode="before")
    @classmethod
    def normalize_scope(cls, v: RuntimeCapabilityOverrideScope | str) -> RuntimeCapabilityOverrideScope | str:
        return _parse_runtime_enum_or_var(v, RuntimeCapabilityOverrideScope, field_name="scope")

    @field_validator("effective", "add", "drop", mode="before")
    @classmethod
    def coerce_override_capability_lists(cls, v):
        return _coerce_string_list(v)

    @field_validator("effective", "add", "drop")
    @classmethod
    def validate_override_capability_names(cls, v: list[str]) -> list[str]:
        return [_normalize_capability_name(item) for item in v]

    @model_validator(mode="after")
    def validate_override_invariants(self) -> RuntimeProcessCapabilityOverride:
        for field_name in ("effective", "add", "drop"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate runtime capability in override {field_name}")

        subject = self.subject
        has_selector = bool(
            subject.name
            or subject.pid is not None
            or subject.parent_pid is not None
            or subject.user
            or subject.group
            or subject.command
            or subject.working_directory
            or subject.description
            or subject.role != RuntimeProcessRole.OTHER
        )
        if not has_selector:
            raise ValueError(
                "runtime capability override subject must identify a process via at least one of "
                "name, pid, parent_pid, role, user, group, command, working_directory, or description"
            )

        if not (self.effective or self.add or self.drop):
            raise ValueError("runtime capability override must assert at least one of effective, add, or drop")

        return self


class RuntimeCapabilityPolicy(SDLModel):
    """Linux/container capability policy observed for a runtime node."""

    required: list[str] = Field(default_factory=list)
    effective: list[str] = Field(default_factory=list)
    add: list[str] = Field(default_factory=list)
    drop: list[str] = Field(default_factory=list)
    process_overrides: list[RuntimeProcessCapabilityOverride] = Field(default_factory=list)
    description: str = ""

    @field_validator("required", "effective", "add", "drop", mode="before")
    @classmethod
    def coerce_capability_lists(cls, v):
        return _coerce_string_list(v)

    @field_validator("required", "effective", "add", "drop")
    @classmethod
    def validate_capability_names(cls, v: list[str]) -> list[str]:
        return [_normalize_capability_name(item) for item in v]

    @model_validator(mode="after")
    def validate_unique_capabilities(self) -> RuntimeCapabilityPolicy:
        for field_name in ("required", "effective", "add", "drop"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate runtime capability in {field_name}")
        _reject_duplicate_overrides(self.process_overrides)
        return self


def _override_identity_key(override: RuntimeProcessCapabilityOverride) -> tuple:
    """Return a comparable identity tuple for an override.

    The tuple keys on every author-set selector field plus the override's scope.
    Unauthored selector fields (``None`` / empty string / default ``OTHER``
    role) are normalized to ``None`` so they do not anchor the identity — in
    the same spirit as ``_reject_duplicate_keys`` on the container-wide
    runtime configuration. Differing scopes for the same selector tuple
    remain distinct policy assertions.
    """
    subject = override.subject
    return (
        subject.name or None,
        subject.pid,
        subject.parent_pid,
        subject.user or None,
        subject.group or None,
        tuple(subject.command) if subject.command else None,
        subject.working_directory or None,
        subject.role if subject.role != RuntimeProcessRole.OTHER else None,
        override.scope,
    )


def _reject_duplicate_overrides(overrides: list[RuntimeProcessCapabilityOverride]) -> None:
    """Raise ``ValueError`` if two overrides assert the same subject + scope.

    The override invariants on each record already require at least one
    selector field; this check exists to catch overrides whose *every*
    author-set field plus scope coincide — two such records are conflicting
    claims about the same subject.
    """
    seen: set[tuple] = set()
    for override in overrides:
        key = _override_identity_key(override)
        if all(part is None for part in key[:-1]):
            # Should not happen — ``validate_override_invariants`` requires
            # at least one selector — but guard against future regressions.
            continue
        if key in seen:
            subject = override.subject
            raise ValueError(
                f"Duplicate runtime capability override for subject "
                f"{subject.name or subject.pid or '<anonymous>'!r} at scope {override.scope}"
            )
        seen.add(key)

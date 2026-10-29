"""Installed inputs for finite modular-control runtime probes.

Harnesses are trusted operator code. They provide inputs and observations, never
verdicts. No module or executable is loaded from a scenario or a report.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from raes_runtime.control_plane import ControlPlaneIdentity, ControlPlaneOptions, RuntimeControlPlane
from raes_runtime.registry import RuntimeTarget


class ModularControlOperation(str, Enum):
    ACTION = "action"
    SELECTION_V2 = "selection-v2"
    CONTROL = "control"
    DISPATCH = "dispatch"
    PROJECTION = "projection"
    INJECT = "inject"
    PROVISION = "provision"
    RESOLVE = "resolve"
    REOPEN = "reopen"
    REGISTER_PLAN = "register-plan"


# These are verifier obligations, not a second mechanism/profile registry.
MODULAR_CONTROL_OBLIGATIONS = (
    "applicable-subset",
    "mandatory-coverage",
    "dependency",
    "optional-failure",
    "support-strength",
    "conflict",
    "permissive-influence",
    "strict-denial",
    "phase-decision",
    "non-ifc",
    "authority",
    "stale-cut",
    "duplicate",
    "restart",
    "trigger-bound",
    "final-sink",
    "integrity",
)


@dataclass(frozen=True)
class ModularControlStep:
    operation: ModularControlOperation
    arguments: Mapping[str, object] | Callable[[RuntimeControlPlane, tuple[object, ...]], Mapping[str, object]]
    expect_refusal: bool = False


@dataclass(frozen=True)
class ModularOwnerObservation:
    """A fresh, independently authorized observation of one owner operation.

    The source authenticates these facts under its backend's evidence contract.
    This carrier itself supplies neither authentication nor dispatch authority.
    """

    effect_id: str
    receipt_ref: str
    disposition: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ModularControlCase:
    name: str
    obligation: str
    participant_address: str
    episode_id: str
    options: ControlPlaneOptions
    steps: tuple[ModularControlStep, ...]
    expected_compositions: tuple[str, ...]
    expected_calls: Mapping[str, int]
    expected_effects: Mapping[str, str] = field(default_factory=dict)
    observe: Callable[[RuntimeControlPlane], tuple[ModularOwnerObservation, ...]] | None = None
    cleanup: Callable[[], tuple[str, ...]] | None = None
    identity: ControlPlaneIdentity | None = None


class ModularControlHarness(Protocol):
    def cases(self, target: RuntimeTarget) -> tuple[ModularControlCase, ...]: ...


@dataclass(frozen=True)
class ModularControlEvidence:
    """Machine-readable subset and exact-cut bindings in the existing report."""

    obligation: str
    selected_obligations: tuple[str, ...]
    claimed_effect_kinds: tuple[str, ...]
    excluded_effect_kinds: tuple[str, ...]
    artifact_digests: Mapping[str, str] = field(default_factory=dict)
    support: tuple[Mapping[str, object], ...] = ()
    expected_calls: Mapping[str, int] = field(default_factory=dict)
    actual_calls: Mapping[str, int] = field(default_factory=dict)
    owner_outcomes: Mapping[str, str] = field(default_factory=dict)
    owner_observations: tuple[ModularOwnerObservation, ...] = ()
    reopened: bool = False
    exact_replays: int = 0
    replayed_after_reopen: bool = False
    refusal_causes: tuple[str, ...] = ()

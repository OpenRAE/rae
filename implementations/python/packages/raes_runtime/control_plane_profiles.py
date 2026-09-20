"""Canonical in-process declarations for runtime control-plane operating profiles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class ControlPlaneProfile(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ControlPlaneActorBoundary(str, Enum):
    EMBEDDER = "embedder"
    AUTHENTICATED_HTTP = "authenticated-http"
    UNAVAILABLE = "unavailable"


class RecoveryObservationRequirement(str, Enum):
    NOT_APPLICABLE = "not-applicable"
    OPTIONAL_INDETERMINATE = "optional-indeterminate"
    FUTURE_UNSPECIFIED = "future-unspecified"


class ControlPlaneCapability(str, Enum):
    STORE_EPHEMERAL = "store.ephemeral"
    STORE_DURABLE = "store.durable"
    STORE_ATOMIC_CLAIMS = "store.atomic-claims"
    STORE_ATOMIC_TERMINAL = "store.atomic-terminal"
    STORE_REVISION_CAS = "store.revision-cas"
    STORE_AUDIT = "store.audit"
    STORE_SCOPE_BOUND = "store.scope-bound"
    STORE_OWNER_LEASE = "store.owner-lease"
    CORE_ACTOR_CONTEXT = "core.actor-context"
    CORE_MUTATION_AUTHORITY = "core.mutation-authority"
    CORE_STARTUP_RECONCILIATION = "core.startup-reconciliation"
    HTTP_AUTHENTICATED_IDENTITY = "http.authenticated-identity"
    HTTP_SINGLE_WORKER = "http.single-worker"
    HTTP_BOUNDED_ADMISSION = "http.bounded-admission"
    HTTP_REVISION_READS = "http.revision-reads"


@dataclass(frozen=True)
class ControlPlaneClaim:
    identifier: str
    description: str


@dataclass(frozen=True)
class ControlPlaneProfileDeclaration:
    profile: ControlPlaneProfile
    label: str
    guarantees: tuple[ControlPlaneClaim, ...]
    nonclaims: tuple[ControlPlaneClaim, ...]
    one_target_per_store: bool
    one_run_per_store: bool
    actor_boundary: ControlPlaneActorBoundary
    recovery_observation: RecoveryObservationRequirement
    required_capabilities: frozenset[ControlPlaneCapability]
    available: bool


@dataclass(frozen=True)
class ControlPlaneStoreCapabilities:
    """A store's immutable, store-owned composition facts, not a profile claim."""

    capabilities: frozenset[ControlPlaneCapability]

    def __post_init__(self) -> None:
        if any(
            not isinstance(item, ControlPlaneCapability) or not item.value.startswith("store.")
            for item in self.capabilities
        ):
            raise TypeError("store capabilities must use closed store capability identifiers")
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))


_STORE_COMMON = frozenset(
    {
        ControlPlaneCapability.STORE_ATOMIC_CLAIMS,
        ControlPlaneCapability.STORE_ATOMIC_TERMINAL,
        ControlPlaneCapability.STORE_REVISION_CAS,
        ControlPlaneCapability.STORE_AUDIT,
        ControlPlaneCapability.STORE_SCOPE_BOUND,
    }
)
CORE_CAPABILITIES = frozenset(
    {
        ControlPlaneCapability.CORE_ACTOR_CONTEXT,
        ControlPlaneCapability.CORE_MUTATION_AUTHORITY,
        ControlPlaneCapability.CORE_STARTUP_RECONCILIATION,
    }
)
_P0_REQUIRED = (
    _STORE_COMMON
    | {ControlPlaneCapability.STORE_EPHEMERAL}
    | {
        ControlPlaneCapability.CORE_ACTOR_CONTEXT,
        ControlPlaneCapability.CORE_MUTATION_AUTHORITY,
    }
)
_P1_REQUIRED = (
    _STORE_COMMON
    | {
        ControlPlaneCapability.STORE_DURABLE,
        ControlPlaneCapability.STORE_OWNER_LEASE,
    }
    | CORE_CAPABILITIES
)
_P2_REQUIRED = _P1_REQUIRED | {
    ControlPlaneCapability.HTTP_AUTHENTICATED_IDENTITY,
    ControlPlaneCapability.HTTP_SINGLE_WORKER,
    ControlPlaneCapability.HTTP_BOUNDED_ADMISSION,
    ControlPlaneCapability.HTTP_REVISION_READS,
}


def _claims(*items: tuple[str, str]) -> tuple[ControlPlaneClaim, ...]:
    return tuple(ControlPlaneClaim(identifier, description) for identifier, description in items)


_IN_PROCESS_SAFETY = "One process owns runtime mutation and validation."
_ACTOR_SCOPED_IDEMPOTENCY = "Claims and receipts bind to the actor and scope."
_TARGET_RUN_ISOLATION = "One target and one run occupy a store."
_REVISION_CAS = "Snapshot writes compare the observed revision."
_ATOMIC_AUDIT = "Terminal state and operational audit commit together."
_NO_HIGH_AVAILABILITY = "No availability topology is promised."
_NO_MULTITENANCY = "One store does not multiplex tenants."


_DECLARATIONS: Mapping[ControlPlaneProfile, ControlPlaneProfileDeclaration] = MappingProxyType(
    {
        ControlPlaneProfile.P0: ControlPlaneProfileDeclaration(
            profile=ControlPlaneProfile.P0,
            label="ephemeral",
            guarantees=_claims(
                ("in-process-safety", _IN_PROCESS_SAFETY),
                ("actor-scoped-idempotency", _ACTOR_SCOPED_IDEMPOTENCY),
                ("target-run-isolation", _TARGET_RUN_ISOLATION),
                ("revision-cas", _REVISION_CAS),
                ("atomic-audit", _ATOMIC_AUDIT),
            ),
            nonclaims=_claims(
                ("durability", "Process loss loses the run."),
                ("restart-recovery", "No process-loss recovery is promised."),
                ("multi-owner", "No concurrent process ownership is promised."),
                ("high-availability", _NO_HIGH_AVAILABILITY),
                ("multitenancy", _NO_MULTITENANCY),
            ),
            one_target_per_store=True,
            one_run_per_store=True,
            actor_boundary=ControlPlaneActorBoundary.EMBEDDER,
            recovery_observation=RecoveryObservationRequirement.NOT_APPLICABLE,
            required_capabilities=frozenset(_P0_REQUIRED),
            available=True,
        ),
        ControlPlaneProfile.P1: ControlPlaneProfileDeclaration(
            profile=ControlPlaneProfile.P1,
            label="local durable",
            guarantees=_claims(
                ("in-process-safety", _IN_PROCESS_SAFETY),
                ("actor-scoped-idempotency", _ACTOR_SCOPED_IDEMPOTENCY),
                ("target-run-isolation", _TARGET_RUN_ISOLATION),
                ("revision-cas", _REVISION_CAS),
                ("atomic-audit", _ATOMIC_AUDIT),
                ("durable-state", "Authoritative state survives process loss."),
                ("retained-idempotency", "Durable claims prevent automatic effect replay."),
                ("lease-admission", "One process-bound owner is admitted."),
                ("startup-reconciliation", "Interrupted work is classified without replay."),
            ),
            nonclaims=_claims(
                ("multi-owner", "No concurrent process ownership is promised."),
                ("high-availability", _NO_HIGH_AVAILABILITY),
                ("exactly-once-effects", "External backend effects are not exactly once."),
                ("multitenancy", _NO_MULTITENANCY),
            ),
            one_target_per_store=True,
            one_run_per_store=True,
            actor_boundary=ControlPlaneActorBoundary.EMBEDDER,
            recovery_observation=RecoveryObservationRequirement.OPTIONAL_INDETERMINATE,
            required_capabilities=frozenset(_P1_REQUIRED),
            available=True,
        ),
        ControlPlaneProfile.P2: ControlPlaneProfileDeclaration(
            profile=ControlPlaneProfile.P2,
            label="served",
            guarantees=_claims(
                ("in-process-safety", _IN_PROCESS_SAFETY),
                ("actor-scoped-idempotency", _ACTOR_SCOPED_IDEMPOTENCY),
                ("target-run-isolation", _TARGET_RUN_ISOLATION),
                ("revision-cas", _REVISION_CAS),
                ("atomic-audit", _ATOMIC_AUDIT),
                ("durable-state", "Authoritative state survives process loss."),
                ("retained-idempotency", "Durable claims prevent automatic effect replay."),
                ("lease-admission", "One process-bound owner is admitted."),
                ("startup-reconciliation", "Interrupted work is classified without replay."),
                ("authenticated-transport", "The adapter authenticates its callers."),
                ("actor-bound-disclosure", "Reads bind to the authenticated actor."),
                ("owner-serialized-mutation", "One service owner serializes mutations."),
                ("revision-carrying-reads", "Reads identify the observed snapshot revision."),
            ),
            nonclaims=_claims(
                ("multi-worker", "The adapter does not coordinate multiple workers."),
                ("tls-proxy-deployment", "TLS and proxy topology belong to deployment."),
                ("high-availability", _NO_HIGH_AVAILABILITY),
                ("exactly-once-effects", "External backend effects are not exactly once."),
                ("multitenancy", _NO_MULTITENANCY),
            ),
            one_target_per_store=True,
            one_run_per_store=True,
            actor_boundary=ControlPlaneActorBoundary.AUTHENTICATED_HTTP,
            recovery_observation=RecoveryObservationRequirement.OPTIONAL_INDETERMINATE,
            required_capabilities=frozenset(_P2_REQUIRED),
            available=True,
        ),
        ControlPlaneProfile.P3: ControlPlaneProfileDeclaration(
            profile=ControlPlaneProfile.P3,
            label="coordinated (future)",
            guarantees=(),
            nonclaims=_claims(
                (
                    "future-coordination",
                    "Coordination, fencing, scheduling, cache coherence, and tenant isolation "
                    "require a future decision.",
                ),
            ),
            one_target_per_store=False,
            one_run_per_store=False,
            actor_boundary=ControlPlaneActorBoundary.UNAVAILABLE,
            recovery_observation=RecoveryObservationRequirement.FUTURE_UNSPECIFIED,
            required_capabilities=frozenset(),
            available=False,
        ),
    }
)


def profile_declaration(profile: ControlPlaneProfile) -> ControlPlaneProfileDeclaration:
    """Return the canonical immutable declaration for a closed profile id."""

    if not isinstance(profile, ControlPlaneProfile):
        raise TypeError("control-plane profile must be a ControlPlaneProfile value")
    return _DECLARATIONS[profile]


def select_profile(profile: ControlPlaneProfile) -> ControlPlaneProfileDeclaration:
    declaration = profile_declaration(profile)
    if not declaration.available:
        raise ValueError(f"control-plane profile {profile.value} is unavailable")
    return declaration


def store_capabilities(store: object) -> frozenset[ControlPlaneCapability]:
    declaration = getattr(store, "control_plane_capabilities", None)
    if declaration is None:
        return frozenset()
    if not isinstance(declaration, ControlPlaneStoreCapabilities):
        raise TypeError("control-plane store has an invalid capability declaration")
    return declaration.capabilities


def require_profile_capabilities(
    declaration: ControlPlaneProfileDeclaration,
    available: frozenset[ControlPlaneCapability],
) -> None:
    missing = sorted(item.value for item in declaration.required_capabilities - available)
    if missing:
        raise TypeError(f"control-plane profile {declaration.profile.value} missing capabilities: {', '.join(missing)}")


__all__ = (
    "CORE_CAPABILITIES",
    "ControlPlaneActorBoundary",
    "ControlPlaneCapability",
    "ControlPlaneClaim",
    "ControlPlaneProfile",
    "ControlPlaneProfileDeclaration",
    "ControlPlaneStoreCapabilities",
    "RecoveryObservationRequirement",
    "profile_declaration",
    "require_profile_capabilities",
    "select_profile",
    "store_capabilities",
)

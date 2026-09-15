"""Canonical runtime models for participant resource governance."""

from dataclasses import dataclass

from raes_contracts.contracts.participant_resource_types import ParticipantResourceKind


@dataclass(frozen=True)
class ParticipantResourceOwnerRuntime:
    """Canonical owner identity for participant resource accounting."""

    owner_id: str
    kind: str
    address: str


@dataclass(frozen=True)
class ParticipantResourceDemandRuntime:
    """One canonical resource dimension admitted and enforced at runtime."""

    budget_id: str
    owner_id: str
    owner_kind: str
    owner_address: str
    pool_ref: str
    resource_kind: ParticipantResourceKind
    unit: str
    accounting_mode: str
    meter_profile_ref: str
    limit: int
    reservation: int
    reset: str
    window_ticks: int | None = None
    parent_budget_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    provenance: str = "authored"


@dataclass(frozen=True)
class ParticipantResourceFairnessRuntime:
    """Required scheduling/fairness behavior for one resource vector."""

    policy: str = "legacy_bounded"
    priority_class: str = "standard"
    weight: int = 1
    protected: bool = False
    borrowing: str = "none"
    reclaim: str = "none"
    max_queue_ticks: int = 0
    starvation_bound_ticks: int = 1


__all__ = [
    "ParticipantResourceDemandRuntime",
    "ParticipantResourceFairnessRuntime",
    "ParticipantResourceOwnerRuntime",
]

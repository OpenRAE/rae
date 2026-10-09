"""Canonical runtime models for participant resource governance."""

from dataclasses import dataclass, field

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
    # DSL-121: a tool_invocations dimension counts only these action contracts.
    action_contract_addresses: tuple[str, ...] = ()
    # Authored dimension ref when an explicit view rule discloses the quota.
    participant_disclosure_ref: str | None = None


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


# Profile of an ACT-624 budget on a behavior-specification aggregate; v3
# autonomous budgets keep their policy profile.
PARTICIPANT_INTERACTION_BUDGET_PROFILE = "participant-interaction-budget/v1"


@dataclass(frozen=True)
class ParticipantInteractionBudgetRuntime:
    """ACT-624 interaction budget of one behavior-specification aggregate.

    It has the resource-policy shape that ADR-097 admission and accounting
    read, so a backend that realizes it records the existing budget state and
    event carriers. It governs every action attempt of its participants.
    """

    address: str
    behavior_specification_address: str
    participant_addresses: tuple[str, ...]
    resource_owners: tuple[ParticipantResourceOwnerRuntime, ...]
    resource_demands: tuple[ParticipantResourceDemandRuntime, ...]
    resource_fairness: ParticipantResourceFairnessRuntime = field(default_factory=ParticipantResourceFairnessRuntime)
    clock_address: str = ""
    profile: str = PARTICIPANT_INTERACTION_BUDGET_PROFILE


__all__ = [
    "PARTICIPANT_INTERACTION_BUDGET_PROFILE",
    "ParticipantInteractionBudgetRuntime",
    "ParticipantResourceDemandRuntime",
    "ParticipantResourceFairnessRuntime",
    "ParticipantResourceOwnerRuntime",
]

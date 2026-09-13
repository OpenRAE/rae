"""Authored participant resource-budget and fairness policy."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, field_validator, model_validator
from raes_contracts.domain_profiles import DomainProfileCoordinateModel

from ._base import SDLModel
from ._identifiers import PortableIdentifier


class ParticipantResourceOwnerKind(str, Enum):
    PARTICIPANT = "participant"
    DEPLOYMENT_TENANT = "deployment_tenant"
    SHARED_SERVICE = "shared_service"
    FLEET = "fleet"


class ParticipantResourceKind(str, Enum):
    ACTION_RATE = "action_rate"
    CONCURRENT_ACTIONS = "concurrent_actions"
    STORAGE_GROWTH = "storage_growth"
    INFERENCE_TOKENS = "inference_tokens"
    IMAGE_GENERATIONS = "image_generations"
    ACCELERATOR = "accelerator"


class ParticipantResourceAccountingMode(str, Enum):
    WINDOWED_COUNTER = "windowed_counter"
    CUMULATIVE_COUNTER = "cumulative_counter"
    RESERVABLE_GAUGE = "reservable_gauge"
    GROWTH_COUNTER = "growth_counter"
    LEASE = "lease"


class ParticipantResourceResetMode(str, Enum):
    EPISODE = "episode"
    TIME_SEGMENT = "time_segment"
    RUN = "run"
    RECONCILED = "reconciled"


class ParticipantResourceOwner(SDLModel):
    kind: ParticipantResourceOwnerKind
    ref: str = Field(min_length=1)


class ParticipantResourceFairness(SDLModel):
    policy: str = Field(min_length=1)
    priority_class: str = Field(min_length=1)
    weight: int = Field(ge=1, le=1_000_000)
    protected: bool
    borrowing: str = Field(min_length=1)
    reclaim: str = Field(min_length=1)
    max_queue_ticks: int = Field(ge=0, le=1_000_000_000)
    starvation_bound_ticks: int = Field(ge=1, le=1_000_000_000)


class ParticipantResourceBudgetDimension(SDLModel):
    owner_ref: PortableIdentifier
    pool_ref: str = Field(min_length=1)
    resource_kind: ParticipantResourceKind | DomainProfileCoordinateModel
    unit: str = Field(min_length=1)
    accounting_mode: ParticipantResourceAccountingMode
    meter_profile_ref: str = Field(min_length=1)
    limit: int = Field(ge=1, le=10**18)
    reservation: int = Field(ge=1, le=10**18)
    reset: ParticipantResourceResetMode
    window_ticks: int | None = Field(default=None, ge=1, le=1_000_000_000)
    parent_budget_ref: PortableIdentifier | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=1024)

    @field_validator("evidence_refs")
    @classmethod
    def _unique_evidence_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("resource-budget evidence refs must be non-empty")
        if len(values) != len(set(values)):
            raise ValueError("resource-budget evidence refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_dimension(self) -> ParticipantResourceBudgetDimension:
        from raes_contracts.contracts.participant_resource_types import require_quantity_semantics

        require_quantity_semantics(
            getattr(self.resource_kind, "value", self.resource_kind), self.unit, self.accounting_mode.value
        )
        if self.reservation > self.limit:
            raise ValueError("resource-budget reservation cannot exceed limit")
        windowed = self.accounting_mode == ParticipantResourceAccountingMode.WINDOWED_COUNTER
        if windowed != (self.window_ticks is not None):
            raise ValueError("windowed resource budgets require window_ticks and other modes forbid it")
        if self.resource_kind == ParticipantResourceKind.STORAGE_GROWTH and (
            self.reset != ParticipantResourceResetMode.RECONCILED
        ):
            raise ValueError("storage_growth resource budget requires reconciled reset")
        return self


def _dimension_semantics(dimension: ParticipantResourceBudgetDimension) -> tuple[object, ...]:
    return (
        dimension.resource_kind,
        dimension.unit,
        dimension.accounting_mode,
        dimension.meter_profile_ref,
    )


def _visit_parent_budget(
    dimensions: dict[PortableIdentifier, ParticipantResourceBudgetDimension],
    budget_id: str,
    visiting: set[str],
    visited: set[str],
) -> None:
    if budget_id in visiting:
        raise ValueError("resource-budget parent aggregation graph must be acyclic")
    if budget_id in visited:
        return
    visiting.add(budget_id)
    dimension = dimensions[budget_id]
    parent_ref = dimension.parent_budget_ref
    if parent_ref is not None:
        parent = dimensions[parent_ref]
        if _dimension_semantics(dimension) != _dimension_semantics(parent):
            raise ValueError("resource-budget parent must use the same resource, unit, mode, and meter")
        if dimension.limit > parent.limit:
            raise ValueError("resource-budget child limit cannot exceed its parent")
        _visit_parent_budget(dimensions, str(parent_ref), visiting, visited)
    visiting.remove(budget_id)
    visited.add(budget_id)


def _validate_sibling_limits(
    dimensions: dict[PortableIdentifier, ParticipantResourceBudgetDimension],
) -> None:
    children_by_parent: dict[str, list[ParticipantResourceBudgetDimension]] = {}
    for dimension in dimensions.values():
        if dimension.parent_budget_ref is not None:
            children_by_parent.setdefault(str(dimension.parent_budget_ref), []).append(dimension)
    for parent_id, children in children_by_parent.items():
        if sum(child.limit for child in children) > dimensions[parent_id].limit:
            raise ValueError("resource-budget sibling limits cannot exceed their parent limit")


class ParticipantResourceBudgetPolicy(SDLModel):
    policy_id: PortableIdentifier
    owners: dict[PortableIdentifier, ParticipantResourceOwner] = Field(min_length=1, max_length=1024)
    fairness: ParticipantResourceFairness
    dimensions: dict[PortableIdentifier, ParticipantResourceBudgetDimension] = Field(
        min_length=1,
        max_length=4096,
    )

    @model_validator(mode="after")
    def _validate_policy(self) -> ParticipantResourceBudgetPolicy:
        required_kinds = set(ParticipantResourceKind)
        actual_kinds = {dimension.resource_kind for dimension in self.dimensions.values()}
        missing = sorted(kind.value for kind in required_kinds - actual_kinds)
        if missing:
            raise ValueError("resource budget requires complete resource vector: " + ", ".join(missing))
        for budget_id, dimension in self.dimensions.items():
            if dimension.owner_ref not in self.owners:
                raise ValueError(f"resource budget {budget_id!r} has unknown owner_ref")
            if dimension.parent_budget_ref is not None and dimension.parent_budget_ref not in self.dimensions:
                raise ValueError(f"resource budget {budget_id!r} has unknown parent_budget_ref")
            owner = self.owners[dimension.owner_ref]
            if owner.kind != ParticipantResourceOwnerKind.PARTICIPANT and (
                dimension.reset == ParticipantResourceResetMode.EPISODE
            ):
                raise ValueError("only participant-owned resource budgets may reset with an episode")
        self._validate_parent_graph()
        pool_keys = [
            (
                dimension.pool_ref,
                self.owners[dimension.owner_ref].kind,
                self.owners[dimension.owner_ref].ref,
                dimension.resource_kind,
                dimension.unit,
                dimension.accounting_mode,
                dimension.meter_profile_ref,
            )
            for dimension in self.dimensions.values()
        ]
        if len(pool_keys) != len(set(pool_keys)):
            raise ValueError("resource-budget dimensions cannot alias the same canonical resource pool")
        return self

    def _validate_parent_graph(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        for budget_id in self.dimensions:
            _visit_parent_budget(self.dimensions, str(budget_id), visiting, visited)
        _validate_sibling_limits(self.dimensions)


__all__ = [
    "ParticipantResourceAccountingMode",
    "ParticipantResourceBudgetDimension",
    "ParticipantResourceBudgetPolicy",
    "ParticipantResourceFairness",
    "ParticipantResourceKind",
    "ParticipantResourceOwner",
    "ParticipantResourceOwnerKind",
    "ParticipantResourceResetMode",
]

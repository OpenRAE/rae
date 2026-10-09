"""Authored participant resource-budget and fairness policy."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from enum import Enum
from typing import ClassVar

from pydantic import Field, field_validator, model_validator
from raes_contracts.domain_profiles import DomainProfileCoordinateModel

from ._base import SDLModel
from ._identifiers import PortableIdentifier
from .semantics._domain_topology_types import resolve_section_ref


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
    INTERACTION_STEPS = "interaction_steps"
    INTERACTION_TURNS = "interaction_turns"
    TOOL_INVOCATIONS = "tool_invocations"
    SCENARIO_TIME = "scenario_time"


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
    tool_affordance_refs: list[PortableIdentifier] = Field(default_factory=list, max_length=256)

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
        from raes_contracts.contracts.participant_resource_types import (
            require_demand_semantics,
            require_quantity_semantics,
        )

        resource_kind = getattr(self.resource_kind, "value", self.resource_kind)
        require_quantity_semantics(resource_kind, self.unit, self.accounting_mode.value, self.meter_profile_ref)
        require_demand_semantics(
            resource_kind,
            self.reset.value,
            self.tool_affordance_refs,
            scope_field="tool_affordance_refs",
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


# A namespaced import renders a dotted spec name, so only the budget id is a
# single segment (PortableIdentifier has no dots).
_DIMENSION_REFERENCE = re.compile(
    r"^behavior_specifications\.(?P<spec>.+)\.autonomous_execution\.resource_budget\.dimensions\.(?P<budget>[^.]+)$"
)


def resource_budget_dimension_reference(spec_name: str, budget_id: str) -> str:
    """Return the stable authored reference for one v3 resource-budget dimension."""

    return f"behavior_specifications.{spec_name}.autonomous_execution.resource_budget.dimensions.{budget_id}"


def is_resource_budget_dimension_reference(ref: object) -> bool:
    """Return whether ``ref`` has the shape of a resource-budget dimension reference."""

    return isinstance(ref, str) and _DIMENSION_REFERENCE.match(ref) is not None


def _enum_value(item: object) -> str:
    return str(getattr(item, "value", item))


def is_resource_budget_view_rule(rule: object) -> bool:
    """Return whether a view rule classifies information as a resource-budget quota."""

    return _enum_value(getattr(rule, "boundary_class", None)) == "resource_budget"


def disclosed_resource_budget_refs(boundary: object) -> frozenset[str]:
    """Return the dimension refs a boundary's resource_budget view rules disclose (DSL-121, EBM-07)."""

    return frozenset(
        str(rule.information_ref)
        for rule in getattr(boundary, "view_rules", ())
        if is_resource_budget_view_rule(rule) and _enum_value(rule.disposition) == "disclosed"
    )


def _resolved_action_contracts(refs: Iterable[object], action_contracts: Mapping[str, object]) -> tuple[str, ...]:
    resolved = (resolve_section_ref(str(ref), "action_contracts", action_contracts) for ref in refs)
    return tuple(dict.fromkeys(key for key in resolved if key is not None))


def dispatched_action_contracts(policy: object, action_contracts: Mapping[str, object]) -> tuple[str, ...]:
    """Return the action-contract keys an autonomous policy dispatches, in compilation order."""

    candidates = getattr(policy, "action_candidates", None)
    refs = (
        [candidate.action_ref for _, candidate in sorted(candidates.items())]
        if candidates
        else list(getattr(policy, "action_order", ()))
    )
    return _resolved_action_contracts(refs, action_contracts)


def specification_action_contracts(behavior_spec: object, action_contracts: Mapping[str, object]) -> tuple[str, ...]:
    """Return the action-contract keys a behavior specification declares for its participants."""

    return _resolved_action_contracts(getattr(behavior_spec, "action_contract_refs", ()), action_contracts)


def tool_affordance_action_contracts(
    behavior_spec: object,
    affordance_id: str,
    governed_actions: Iterable[str],
    action_contracts: Mapping[str, object],
) -> tuple[str, ...] | None:
    """Return the governed action contracts one tool affordance makes countable.

    The affordance is the authoring contract that makes an invocation of its
    tool equal to an attempt of its action contracts (DSL-121). Only governed
    actions are attempts the budget counts: those an autonomous policy
    dispatches, or those a behavior specification declares for an aggregate
    budget (ACT-624). ``None`` means the behavior specification declares no
    such affordance.
    """

    affordance = getattr(behavior_spec, "tool_affordances", {}).get(affordance_id)
    if affordance is None:
        return None
    bound = set(_resolved_action_contracts(affordance.action_contract_refs, action_contracts))
    return tuple(key for key in governed_actions if key in bound)


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
        if not set(dimension.tool_affordance_refs) <= set(parent.tool_affordance_refs):
            raise ValueError("resource-budget child tool_affordance_refs must be within its parent's")
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


def _owner_identity(owner: ParticipantResourceOwner) -> tuple[ParticipantResourceOwnerKind, str]:
    ref = owner.ref.removeprefix("agents.") if owner.kind == ParticipantResourceOwnerKind.PARTICIPANT else owner.ref
    return owner.kind, ref


class ParticipantResourceBudgetPolicy(SDLModel):
    # The v3 autonomous profile governs every scheduler resource, so it must
    # declare the complete initial ADR-097 vector.
    _requires_complete_vector: ClassVar[bool] = True

    policy_id: PortableIdentifier
    owners: dict[PortableIdentifier, ParticipantResourceOwner] = Field(min_length=1, max_length=1024)
    fairness: ParticipantResourceFairness
    dimensions: dict[PortableIdentifier, ParticipantResourceBudgetDimension] = Field(
        min_length=1,
        max_length=4096,
    )

    @model_validator(mode="after")
    def _validate_policy(self) -> ParticipantResourceBudgetPolicy:
        if self._requires_complete_vector:
            self._validate_complete_vector()
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
        self._validate_parent_owners()
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

    def _validate_complete_vector(self) -> None:
        from raes_contracts.contracts.participant_resource_types import REQUIRED_RESOURCE_KINDS

        actual_kinds = {
            dimension.resource_kind.value
            for dimension in self.dimensions.values()
            if isinstance(dimension.resource_kind, ParticipantResourceKind)
        }
        missing = sorted(REQUIRED_RESOURCE_KINDS - actual_kinds)
        if missing:
            raise ValueError("resource budget requires complete resource vector: " + ", ".join(missing))

    def _validate_parent_graph(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        for budget_id in self.dimensions:
            _visit_parent_budget(self.dimensions, str(budget_id), visiting, visited)
        _validate_sibling_limits(self.dimensions)

    def _validate_parent_owners(self) -> None:
        """Keep shared and global use out of participant-local budgets (SEM-223 EBM-03)."""

        for budget_id, dimension in self.dimensions.items():
            if dimension.parent_budget_ref is None:
                continue
            parent_owner = self.owners[self.dimensions[dimension.parent_budget_ref].owner_ref]
            if parent_owner.kind == ParticipantResourceOwnerKind.PARTICIPANT and (
                _owner_identity(self.owners[dimension.owner_ref]) != _owner_identity(parent_owner)
            ):
                raise ValueError(
                    f"resource budget {budget_id!r} cannot aggregate into a participant-owned parent of another owner"
                )


def _needs_shared_clock(dimension: ParticipantResourceBudgetDimension) -> bool:
    return (
        dimension.resource_kind == ParticipantResourceKind.SCENARIO_TIME
        or dimension.reset == ParticipantResourceResetMode.TIME_SEGMENT
        or dimension.window_ticks is not None
    )


class ParticipantInteractionBudget(ParticipantResourceBudgetPolicy):
    """ACT-624 budget policy on a behavior specification; bounds only its declared dimensions."""

    # The ADR-097 budget policy, not a second budget family: it governs every
    # participant its specification selects, whatever their implementation
    # kind. Ticks, time segments, and windows are counted on ``clock_ref``.
    _requires_complete_vector: ClassVar[bool] = False

    clock_ref: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate_clock_basis(self) -> ParticipantInteractionBudget:
        if any(_needs_shared_clock(dimension) for dimension in self.dimensions.values()) != (
            self.clock_ref is not None
        ):
            raise ValueError(
                "interaction budget clock_ref is required exactly when a dimension counts scenario time, "
                "resets per time segment, or uses a window"
            )
        return self


__all__ = [
    "ParticipantInteractionBudget",
    "ParticipantResourceAccountingMode",
    "ParticipantResourceBudgetDimension",
    "ParticipantResourceBudgetPolicy",
    "ParticipantResourceFairness",
    "ParticipantResourceKind",
    "ParticipantResourceOwner",
    "ParticipantResourceOwnerKind",
    "ParticipantResourceResetMode",
    "dispatched_action_contracts",
    "disclosed_resource_budget_refs",
    "is_resource_budget_dimension_reference",
    "is_resource_budget_view_rule",
    "resource_budget_dimension_reference",
    "specification_action_contracts",
    "tool_affordance_action_contracts",
]

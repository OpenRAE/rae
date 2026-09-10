"""Closed SDL scenario-family variation declarations (ADR-084)."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, WithJsonSchema, model_validator
from raes_contracts.bounded_domains import (
    BooleanDomain,
    EnumDomain,
    ExactDomain,
    GovernedReferenceDomain,
    NumericIntervalDomain,
)

from ._base import SDLModel
from ._identifiers import PortableIdentifier, require_qualified_identifier


def _qualified_reference(value: str) -> str:
    return require_qualified_identifier(value, field_name="variation reference")


QualifiedReference = Annotated[
    str,
    AfterValidator(_qualified_reference),
    WithJsonSchema({"type": "string", "minLength": 1, "maxLength": 2048}),
]

VARIATION_SATISFIABILITY_STATE_LIMIT = 100_000

ScalarDomain = Annotated[
    ExactDomain | EnumDomain | BooleanDomain | NumericIntervalDomain,
    Field(discriminator="kind"),
]


class ReferenceTargetSlot(str, Enum):
    """Closed scalar-reference slots whose owners authorize replacement."""

    CONDITION_PROPOSITION = "conditions.proposition"
    CONTENT_TARGET = "content.target"
    ACCOUNT_NODE = "accounts.node"
    ACCOUNT_DOMAIN = "accounts.domain_ref"
    IDENTITY_DOMAIN_AUTHORITY_ACCOUNT = "identity_domains.authority_account_ref"
    OBJECTIVE_AGENT = "objectives.agent"
    OBJECTIVE_ENTITY = "objectives.entity"


class CollectionTargetSlot(str, Enum):
    """Closed finite collection slots whose owning model permits selection."""

    NODE_FEATURES = "nodes.features"
    NODE_CONDITIONS = "nodes.conditions"
    NODE_INJECTS = "nodes.injects"
    EVENT_ASSERTIONS = "events.assertions"
    EVENT_INJECTS = "events.injects"
    STORY_SCRIPTS = "stories.scripts"
    AGENT_STARTING_ACCOUNTS = "agents.starting_accounts"
    AGENT_STARTING_ASSERTIONS = "agents.starting_assertions"
    OBJECTIVE_TARGETS = "objectives.targets"
    OBJECTIVE_DEPENDS_ON = "objectives.depends_on"


class TimingTargetSlot(str, Enum):
    """Closed logical-time fields; none denotes host or scheduler time."""

    CONDITION_INTERVAL = "conditions.interval"
    SCRIPT_START_TIME = "scripts.start_time"
    SCRIPT_END_TIME = "scripts.end_time"
    SCRIPT_SPEED = "scripts.speed"
    STORY_SPEED = "stories.speed"


class LogicalTimingUnit(str, Enum):
    SECONDS = "seconds"
    LOGICAL_TICKS = "logical-ticks"
    MULTIPLIER = "multiplier"


REFERENCE_TARGET_SPECS: dict[ReferenceTargetSlot, tuple[str, str]] = {
    ReferenceTargetSlot.CONDITION_PROPOSITION: ("conditions", "propositions"),
    ReferenceTargetSlot.CONTENT_TARGET: ("content", "nodes"),
    ReferenceTargetSlot.ACCOUNT_NODE: ("accounts", "nodes"),
    ReferenceTargetSlot.ACCOUNT_DOMAIN: ("accounts", "identity_domains"),
    ReferenceTargetSlot.IDENTITY_DOMAIN_AUTHORITY_ACCOUNT: ("identity_domains", "accounts"),
    ReferenceTargetSlot.OBJECTIVE_AGENT: ("objectives", "agents"),
    ReferenceTargetSlot.OBJECTIVE_ENTITY: ("objectives", "entities"),
}

COLLECTION_TARGET_SPECS: dict[CollectionTargetSlot, tuple[str, str]] = {
    CollectionTargetSlot.NODE_FEATURES: ("nodes", "features"),
    CollectionTargetSlot.NODE_CONDITIONS: ("nodes", "conditions"),
    CollectionTargetSlot.NODE_INJECTS: ("nodes", "injects"),
    CollectionTargetSlot.EVENT_ASSERTIONS: ("events", "assertions"),
    CollectionTargetSlot.EVENT_INJECTS: ("events", "injects"),
    CollectionTargetSlot.STORY_SCRIPTS: ("stories", "scripts"),
    CollectionTargetSlot.AGENT_STARTING_ACCOUNTS: ("agents", "accounts"),
    CollectionTargetSlot.AGENT_STARTING_ASSERTIONS: ("agents", "assertions"),
    CollectionTargetSlot.OBJECTIVE_TARGETS: ("objectives", "targetable"),
    CollectionTargetSlot.OBJECTIVE_DEPENDS_ON: ("objectives", "objectives"),
}

TIMING_TARGET_SPECS: dict[TimingTargetSlot, tuple[str, str, LogicalTimingUnit]] = {
    TimingTargetSlot.CONDITION_INTERVAL: ("conditions", "integer", LogicalTimingUnit.SECONDS),
    TimingTargetSlot.SCRIPT_START_TIME: ("scripts", "integer", LogicalTimingUnit.SECONDS),
    TimingTargetSlot.SCRIPT_END_TIME: ("scripts", "integer", LogicalTimingUnit.SECONDS),
    TimingTargetSlot.SCRIPT_SPEED: ("scripts", "number", LogicalTimingUnit.MULTIPLIER),
    TimingTargetSlot.STORY_SPEED: ("stories", "number", LogicalTimingUnit.MULTIPLIER),
}


class VariableTarget(SDLModel):
    kind: Literal["variable"] = "variable"
    variable: QualifiedReference


class ReferenceTarget(SDLModel):
    kind: Literal["reference"] = "reference"
    owner: QualifiedReference
    slot: ReferenceTargetSlot


class CollectionTarget(SDLModel):
    kind: Literal["collection"] = "collection"
    owner: QualifiedReference
    slot: CollectionTargetSlot


class LogicalTimingTarget(SDLModel):
    kind: Literal["logical-timing"] = "logical-timing"
    owner: QualifiedReference
    slot: TimingTargetSlot


class SelectionRelation(SDLModel):
    """A finite cross-point member requirement or exclusion."""

    point: QualifiedReference
    members: list[PortableIdentifier] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_members(self) -> SelectionRelation:
        if len(self.members) != len(set(self.members)):
            raise ValueError("selection relation members must be unique")
        return self


class VariationMember(SDLModel):
    """One named semantic object referenced by a structural point."""

    reference: QualifiedReference
    description: str = ""
    requires: list[SelectionRelation] = Field(default_factory=list)
    excludes: list[SelectionRelation] = Field(default_factory=list)


class OrderPrecedence(SDLModel):
    before: PortableIdentifier
    after: PortableIdentifier

    @model_validator(mode="after")
    def _not_reflexive(self) -> OrderPrecedence:
        if self.before == self.after:
            raise ValueError("order precedence must name distinct members")
        return self


class _OrderConstraintWitness:
    def __init__(
        self,
        names: set[str],
        edges: set[tuple[str, str]],
        fixed_positions: dict[str, int],
    ) -> None:
        self._ordered_names = tuple(sorted(names))
        self._fixed_positions = fixed_positions
        self._fixed_by_position = {position: name for name, position in fixed_positions.items()}
        self._predecessors = {
            name: frozenset(before for before, after in edges if after == name) for name in self._ordered_names
        }
        self._memo: dict[frozenset[str], bool] = {}
        self._explored = 0

    def has_witness(self) -> bool:
        return self._visit(frozenset())

    def _visit(self, placed: frozenset[str]) -> bool:
        cached = self._memo.get(placed)
        if cached is not None:
            return cached
        self._explored += 1
        if self._explored > VARIATION_SATISFIABILITY_STATE_LIMIT:
            raise ValueError("order constraints exceed the deterministic satisfiability budget")
        position = len(placed)
        if position == len(self._ordered_names):
            result = True
        elif self._has_overdue_fixed_member(placed, position):
            result = False
        else:
            result = any(self._candidate_has_witness(name, placed, position) for name in self._candidates(position))
        self._memo[placed] = result
        return result

    def _has_overdue_fixed_member(self, placed: frozenset[str], position: int) -> bool:
        return any(
            fixed_position < position and name not in placed for name, fixed_position in self._fixed_positions.items()
        )

    def _candidates(self, position: int) -> tuple[str, ...]:
        fixed_name = self._fixed_by_position.get(position)
        return (fixed_name,) if fixed_name is not None else self._ordered_names

    def _candidate_has_witness(self, name: str, placed: frozenset[str], position: int) -> bool:
        pinned_position = self._fixed_positions.get(name)
        eligible = (
            name not in placed
            and (pinned_position is None or pinned_position == position)
            and self._predecessors[name].issubset(placed)
        )
        return eligible and self._visit(placed | {name})


def _order_constraints_have_witness(
    names: set[str],
    edges: set[tuple[str, str]],
    fixed_positions: dict[str, int],
) -> bool:
    return _OrderConstraintWitness(names, edges, fixed_positions).has_witness()


def _validated_order_edges(
    names: set[str],
    precedence: list[OrderPrecedence],
) -> set[tuple[str, str]]:
    edges = {(edge.before, edge.after) for edge in precedence}
    if len(edges) != len(precedence):
        raise ValueError("order precedence edges must be unique")
    if any(before not in names or after not in names for before, after in edges):
        raise ValueError("order precedence references an undefined member")
    return edges


def _validate_fixed_positions(names: set[str], fixed_positions: dict[str, int]) -> None:
    if any(name not in names for name in fixed_positions):
        raise ValueError("order fixed_positions references an undefined member")
    positions = list(fixed_positions.values())
    if any(position < 0 or position >= len(names) for position in positions):
        raise ValueError("order fixed position must be within the member range")
    if len(positions) != len(set(positions)):
        raise ValueError("order fixed positions must be unique")


def _order_graph_is_acyclic(names: set[str], edges: set[tuple[str, str]]) -> bool:
    pending = dict.fromkeys(names, 0)
    outgoing: dict[str, list[str]] = {name: [] for name in names}
    for before, after in edges:
        outgoing[before].append(after)
        pending[after] += 1
    ready = [name for name, count in pending.items() if count == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for successor in outgoing[current]:
            pending[successor] -= 1
            if pending[successor] == 0:
                ready.append(successor)
    return visited == len(names)


class ParameterVariationPoint(SDLModel):
    kind: Literal["parameter"] = "parameter"
    target: VariableTarget
    domain: ScalarDomain
    description: str = ""


class GovernedReferenceVariationPoint(SDLModel):
    kind: Literal["governed-reference"] = "governed-reference"
    target: ReferenceTarget
    domain: GovernedReferenceDomain
    description: str = ""


class AlternativeVariationPoint(SDLModel):
    kind: Literal["alternative"] = "alternative"
    target: ReferenceTarget
    alternatives: dict[PortableIdentifier, VariationMember] = Field(min_length=1)
    description: str = ""

    @model_validator(mode="after")
    def _unique_references(self) -> AlternativeVariationPoint:
        references = [member.reference for member in self.alternatives.values()]
        if len(references) != len(set(references)):
            raise ValueError("alternative references must be unique")
        return self


class SubsetVariationPoint(SDLModel):
    kind: Literal["subset"] = "subset"
    target: CollectionTarget
    members: dict[PortableIdentifier, VariationMember] = Field(min_length=1)
    minimum: int = Field(default=0, ge=0)
    maximum: int | None = Field(default=None, ge=0)
    description: str = ""

    @model_validator(mode="after")
    def _validate_bounds(self) -> SubsetVariationPoint:
        upper = len(self.members) if self.maximum is None else self.maximum
        if self.minimum > upper:
            raise ValueError("subset minimum must not exceed maximum")
        if upper > len(self.members):
            raise ValueError("subset maximum must not exceed member count")
        references = [member.reference for member in self.members.values()]
        if len(references) != len(set(references)):
            raise ValueError("subset member references must be unique")
        return self


class OrderVariationPoint(SDLModel):
    kind: Literal["order"] = "order"
    target: CollectionTarget
    members: dict[PortableIdentifier, VariationMember] = Field(min_length=1)
    precedence: list[OrderPrecedence] = Field(default_factory=list)
    fixed_positions: dict[PortableIdentifier, int] = Field(default_factory=dict)
    description: str = ""

    @model_validator(mode="after")
    def _validate_order_constraints(self) -> OrderVariationPoint:
        names = set(self.members)
        references = [member.reference for member in self.members.values()]
        if len(references) != len(set(references)):
            raise ValueError("order member references must be unique")
        edges = _validated_order_edges(names, self.precedence)
        _validate_fixed_positions(names, self.fixed_positions)
        if not _order_graph_is_acyclic(names, edges):
            raise ValueError("order precedence graph must be acyclic")
        if self.fixed_positions and not _order_constraints_have_witness(names, edges, self.fixed_positions):
            raise ValueError("order constraints must admit at least one ordering")
        return self


class LogicalTimingVariationPoint(SDLModel):
    kind: Literal["logical-timing"] = "logical-timing"
    target: LogicalTimingTarget
    domain: ScalarDomain
    unit: LogicalTimingUnit
    description: str = ""


VariationPoint = Annotated[
    ParameterVariationPoint
    | GovernedReferenceVariationPoint
    | AlternativeVariationPoint
    | SubsetVariationPoint
    | OrderVariationPoint
    | LogicalTimingVariationPoint,
    Field(discriminator="kind"),
]


def structural_members(point: VariationPoint) -> dict[PortableIdentifier, VariationMember]:
    if isinstance(point, AlternativeVariationPoint):
        return point.alternatives
    if isinstance(point, (SubsetVariationPoint, OrderVariationPoint)):
        return point.members
    return {}


__all__ = [
    "AlternativeVariationPoint",
    "COLLECTION_TARGET_SPECS",
    "CollectionTarget",
    "CollectionTargetSlot",
    "GovernedReferenceVariationPoint",
    "LogicalTimingTarget",
    "LogicalTimingUnit",
    "LogicalTimingVariationPoint",
    "OrderVariationPoint",
    "ParameterVariationPoint",
    "REFERENCE_TARGET_SPECS",
    "ReferenceTarget",
    "ReferenceTargetSlot",
    "SelectionRelation",
    "SubsetVariationPoint",
    "TIMING_TARGET_SPECS",
    "TimingTargetSlot",
    "VARIATION_SATISFIABILITY_STATE_LIMIT",
    "VariableTarget",
    "VariationMember",
    "VariationPoint",
    "structural_members",
]

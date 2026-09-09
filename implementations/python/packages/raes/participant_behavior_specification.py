"""First-class participant behavior specification models (ACT-606)."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated

from pydantic import Field, StrictInt, field_validator, model_validator
from typing_extensions import TypeAliasType

from ._base import SDLModel
from ._classification_guard import LegacyClassificationGuard
from ._identifiers import PortableIdentifier
from .participant_execution import ParticipantAutonomousExecutionPolicy
from .participant_inject_delivery import ParticipantInjectDelivery


class ParticipantBehaviorSpecificationLifecycle(str, Enum):
    """Governance lifecycle for participant behavior specifications."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


_BEHAVIOR_SPEC_EXTENSION_KEY_RE = re.compile(r"^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*$")
_BEHAVIOR_SPEC_EXTENSION_POLICIES = frozenset({"closed", "governed-extension"})
BehaviorSpecificationExtensionScalar = str | int | float | bool | None
BehaviorSpecificationExtensionValue = TypeAliasType(
    "BehaviorSpecificationExtensionValue",
    BehaviorSpecificationExtensionScalar
    | list["BehaviorSpecificationExtensionValue"]
    | dict[str, "BehaviorSpecificationExtensionValue"],
)
ToolAffordanceReference = Annotated[str, Field(min_length=1, pattern=r"\S")]


class ParticipantToolAffordance(SDLModel):
    """Authored participant-local binding from tool identity to governed behavior."""

    tool_ref: str | None = Field(default=None, min_length=1)
    action_contract_refs: list[ToolAffordanceReference] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    observation_boundary_refs: list[ToolAffordanceReference] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )

    @field_validator("action_contract_refs", "observation_boundary_refs")
    @classmethod
    def _require_unique_non_empty_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("tool affordance refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("tool affordance refs must be unique within each field")
        return values


def tool_affordance_reference(spec_name: str, affordance_id: str) -> str:
    """Return the stable authored reference for one nested affordance binding."""

    return f"behavior_specifications.{spec_name}.tool_affordances.{affordance_id}"


class MixedControlOrderStrategy(str, Enum):
    """Portable ordering strategies for authored control decisions."""

    TOTAL_EFFECTIVE_ORDER = "total-effective-order"


class MixedControlTransitionKind(str, Enum):
    """Control-owned facts kept distinct from admission and execution."""

    PROPOSAL = "proposal"
    APPROVAL = "approval"
    DENIAL = "denial"
    EXTERNAL_DIRECTION = "external-direction"
    INTERVENTION = "intervention"
    HANDOFF = "handoff"
    OVERRIDE = "override"
    CANCELLATION = "cancellation"


class MixedControlAuthorityStatus(str, Enum):
    """Authored authority state for one controller binding."""

    ACTIVE = "active"
    REVOKED = "revoked"


class MixedControlDuplicateDisposition(str, Enum):
    """Disposition for a repeated decision identity."""

    IDEMPOTENT_IF_EQUIVALENT = "idempotent-if-equivalent"


class MixedControlRejectDisposition(str, Enum):
    """Fail-closed disposition that preserves the current state."""

    REJECT_NO_STATE_CHANGE = "reject-no-state-change"


class MixedControlConcurrentDisposition(str, Enum):
    """Disposition for decisions that share a control-state revision."""

    ORDER_THEN_REVALIDATE = "order-then-revalidate"


class MixedControlDispositionRules(SDLModel):
    """Explicit deterministic rules for invalid or competing decisions."""

    duplicate: MixedControlDuplicateDisposition
    stale: MixedControlRejectDisposition
    revoked: MixedControlRejectDisposition
    late: MixedControlRejectDisposition
    concurrent: MixedControlConcurrentDisposition
    conflict: MixedControlRejectDisposition


class MixedControlControllerState(SDLModel):
    """One authored controller, authority, scope, and validity binding."""

    controller_ref: str
    authority_basis_refs: list[str]
    scope_refs: list[str]
    policy_revision: str
    valid_from_order: StrictInt = Field(ge=0)
    valid_until_order: StrictInt = Field(ge=0)
    authority_status: MixedControlAuthorityStatus
    evidence_refs: list[str]

    @field_validator("controller_ref", "policy_revision")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mixed-control controller-state fields must be non-empty")
        return value

    @field_validator("authority_basis_refs", "scope_refs", "evidence_refs")
    @classmethod
    def _require_unique_non_empty_refs(cls, values: list[str]) -> list[str]:
        if not values or any(not value.strip() for value in values):
            raise ValueError("mixed-control controller-state refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("mixed-control controller-state refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_interval(self) -> MixedControlControllerState:
        if self.valid_until_order < self.valid_from_order:
            raise ValueError("mixed-control controller-state validity interval must not be inverted")
        return self


_PROPOSAL_TARGETING_KINDS = frozenset(
    {
        MixedControlTransitionKind.APPROVAL,
        MixedControlTransitionKind.DENIAL,
        MixedControlTransitionKind.EXTERNAL_DIRECTION,
    }
)


class MixedControlTransition(SDLModel):
    """One authored, revision-checked mixed-control transition declaration."""

    transition_kind: MixedControlTransitionKind
    from_state_ref: PortableIdentifier
    to_state_ref: PortableIdentifier
    policy_revision: str
    expected_state_revision: StrictInt = Field(ge=0)
    resulting_state_revision: StrictInt = Field(ge=1)
    effective_order: StrictInt = Field(ge=0)
    valid_from_order: StrictInt = Field(ge=0)
    valid_until_order: StrictInt = Field(ge=0)
    proposal_ref: PortableIdentifier | None = None
    proposal_revision: StrictInt | None = Field(default=None, ge=1)
    evidence_refs: list[str]
    completion_evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("policy_revision")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mixed-control transition policy_revision must be non-empty")
        return value

    @field_validator("evidence_refs", "completion_evidence_refs")
    @classmethod
    def _require_unique_non_empty_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("mixed-control transition evidence refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("mixed-control transition evidence refs must be unique")
        return values

    @model_validator(mode="after")
    def _validate_transition_shape(self) -> MixedControlTransition:
        self._validate_transition_ordering()
        self._validate_proposal_targeting()
        self._validate_transition_kind_requirements()
        return self

    def _validate_transition_ordering(self) -> None:
        if not self.evidence_refs:
            raise ValueError("mixed-control transitions require evidence_refs")
        if self.valid_until_order < self.valid_from_order:
            raise ValueError("mixed-control transition validity interval must not be inverted")
        if not self.valid_from_order <= self.effective_order <= self.valid_until_order:
            raise ValueError("mixed-control transition effective_order must fall within its validity interval")
        if self.resulting_state_revision != self.expected_state_revision + 1:
            raise ValueError("mixed-control transitions must advance state revision by exactly one")

    def _validate_proposal_targeting(self) -> None:
        has_proposal = self.proposal_ref is not None or self.proposal_revision is not None
        if (self.proposal_ref is None) != (self.proposal_revision is None):
            raise ValueError("mixed-control proposal_ref and proposal_revision must be provided together")
        if self.transition_kind in _PROPOSAL_TARGETING_KINDS and not has_proposal:
            raise ValueError(f"{self.transition_kind.value} transitions require a proposal_ref and revision")
        if self.transition_kind == MixedControlTransitionKind.PROPOSAL and has_proposal:
            raise ValueError("proposal transitions cannot target another proposal")

    def _validate_transition_kind_requirements(self) -> None:
        if self.transition_kind == MixedControlTransitionKind.HANDOFF and not self.completion_evidence_refs:
            raise ValueError("handoff transitions require completion_evidence_refs")


class MixedControlParticipantOperation(SDLModel):
    """Closed authored mixed-control policy for exactly one participant."""

    participant_ref: str
    policy_revision: str
    order_strategy: MixedControlOrderStrategy
    initial_state_ref: PortableIdentifier
    dispositions: MixedControlDispositionRules
    controller_states: dict[PortableIdentifier, MixedControlControllerState]
    transitions: dict[PortableIdentifier, MixedControlTransition]

    @field_validator("participant_ref", "policy_revision")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mixed-control participant and policy revision must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_policy_graph(self) -> MixedControlParticipantOperation:
        self._validate_graph_roots()
        self._validate_controller_state_revisions()
        ordered_transitions = self._validated_ordered_transitions()
        self._validate_revision_continuity(ordered_transitions)
        self._validate_proposal_links(ordered_transitions)
        return self

    def _validate_graph_roots(self) -> None:
        if not self.controller_states:
            raise ValueError("mixed_control requires controller_states")
        if not self.transitions:
            raise ValueError("mixed_control requires transitions")
        if self.initial_state_ref not in self.controller_states:
            raise ValueError("mixed_control initial_state_ref must resolve to controller_states")

    def _validate_controller_state_revisions(self) -> None:
        for state_id, state in self.controller_states.items():
            if state.policy_revision != self.policy_revision:
                raise ValueError(f"mixed-control controller state '{state_id}' has a stale policy revision")

    def _validated_ordered_transitions(self) -> list[tuple[PortableIdentifier, MixedControlTransition]]:
        effective_orders: set[int] = set()
        ordered_transitions: list[tuple[PortableIdentifier, MixedControlTransition]] = []
        for transition_id, transition in self.transitions.items():
            if transition.policy_revision != self.policy_revision:
                raise ValueError(f"mixed-control transition '{transition_id}' has a stale policy revision")
            state_refs = (transition.from_state_ref, transition.to_state_ref)
            if any(ref not in self.controller_states for ref in state_refs):
                raise ValueError(f"mixed-control transition '{transition_id}' has an unknown controller-state ref")
            if transition.effective_order in effective_orders:
                raise ValueError("mixed-control transitions require unique effective_order values")
            effective_orders.add(transition.effective_order)
            ordered_transitions.append((transition_id, transition))
        return sorted(ordered_transitions, key=lambda item: item[1].effective_order)

    def _validate_revision_continuity(
        self,
        ordered_transitions: list[tuple[PortableIdentifier, MixedControlTransition]],
    ) -> None:
        established_state_revisions = {(self.initial_state_ref, 0)}
        for transition_id, transition in ordered_transitions:
            expected_state = (transition.from_state_ref, transition.expected_state_revision)
            if expected_state not in established_state_revisions:
                raise ValueError(
                    f"mixed-control transition '{transition_id}' expected state revision "
                    f"{transition.expected_state_revision} is not established for controller state "
                    f"'{transition.from_state_ref}'"
                )
            established_state_revisions.add((transition.to_state_ref, transition.resulting_state_revision))

    def _validate_proposal_links(
        self,
        ordered_transitions: list[tuple[PortableIdentifier, MixedControlTransition]],
    ) -> None:
        for transition_id, transition in ordered_transitions:
            if transition.proposal_ref is None:
                continue
            proposal = self.transitions.get(transition.proposal_ref)
            if proposal is None or proposal.transition_kind != MixedControlTransitionKind.PROPOSAL:
                raise ValueError(f"mixed-control transition '{transition_id}' proposal_ref must target a proposal")
            if transition.proposal_revision != proposal.resulting_state_revision:
                raise ValueError(f"mixed-control transition '{transition_id}' has a stale proposal revision")
            if transition.effective_order <= proposal.effective_order:
                raise ValueError(f"mixed-control transition '{transition_id}' must follow its proposal")


class ParticipantBehaviorSpecification(LegacyClassificationGuard):
    """First-class authored aggregate over participant behavior surfaces."""

    legacy_classification_fields = ("ai_offensive_behavior_refs", "defensive_behavior_refs", "offensive_behavior_refs")

    semantic_version: str
    lifecycle_state: ParticipantBehaviorSpecificationLifecycle = ParticipantBehaviorSpecificationLifecycle.ACTIVE
    participant_refs: list[str] = Field(default_factory=list)
    participant_role_refs: list[str] = Field(default_factory=list)
    action_contract_refs: list[str] = Field(default_factory=list)
    observation_boundary_refs: list[str] = Field(default_factory=list)
    outcome_interpretation_rule_refs: list[str] = Field(default_factory=list)
    authority_scope_refs: list[str] = Field(default_factory=list)
    behavior_mode: str | None = None
    autonomous_execution: ParticipantAutonomousExecutionPolicy | None = None
    mixed_control: MixedControlParticipantOperation | None = None
    realization_profile_ref: str | None = None
    backend_feature_support_refs: list[str] = Field(default_factory=list)
    evidence_contract_refs: list[str] = Field(default_factory=list)
    tool_affordances: dict[PortableIdentifier, ParticipantToolAffordance] = Field(
        default_factory=dict,
        json_schema_extra={"additionalProperties": False},
    )
    participant_inject_deliveries: dict[PortableIdentifier, ParticipantInjectDelivery] = Field(
        default_factory=dict,
        json_schema_extra={"additionalProperties": False},
    )
    extension_policy: str = "governed-extension"
    extensions: dict[str, BehaviorSpecificationExtensionValue] = Field(default_factory=dict)

    @field_validator("semantic_version", "extension_policy")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("behavior specification fields must be non-empty")
        return value

    @field_validator("behavior_mode", "realization_profile_ref")
    @classmethod
    def _require_optional_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("behavior specification optional fields must be non-empty when provided")
        return value

    @field_validator(
        "participant_refs",
        "participant_role_refs",
        "action_contract_refs",
        "observation_boundary_refs",
        "outcome_interpretation_rule_refs",
        "authority_scope_refs",
        "backend_feature_support_refs",
        "evidence_contract_refs",
    )
    @classmethod
    def _require_unique_non_empty_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("behavior specification refs must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("behavior specification refs must be unique within each field")
        return values

    @field_validator("extensions")
    @classmethod
    def _validate_extension_keys(
        cls, values: dict[str, BehaviorSpecificationExtensionValue]
    ) -> dict[str, BehaviorSpecificationExtensionValue]:
        invalid = sorted(key for key in values if not _BEHAVIOR_SPEC_EXTENSION_KEY_RE.fullmatch(key))
        if invalid:
            joined = ", ".join(invalid)
            raise ValueError(
                "behavior specification extension keys must match x-<owner>:<term> governed extension syntax: " + joined
            )
        return values

    @model_validator(mode="after")
    def _validate_aggregate_shape(self) -> ParticipantBehaviorSpecification:
        if self.extension_policy not in _BEHAVIOR_SPEC_EXTENSION_POLICIES:
            allowed = ", ".join(sorted(_BEHAVIOR_SPEC_EXTENSION_POLICIES))
            raise ValueError(f"behavior specification extension_policy must be one of: {allowed}")
        if self.extension_policy == "closed" and self.extensions:
            raise ValueError("behavior specification extensions require extension_policy governed-extension")
        if not self.participant_refs and not self.participant_role_refs:
            raise ValueError("behavior specifications require participant_refs or participant_role_refs")
        if not any(
            (
                self.action_contract_refs,
                self.observation_boundary_refs,
                self.outcome_interpretation_rule_refs,
                self.authority_scope_refs,
                self.behavior_mode,
                self.autonomous_execution,
                self.mixed_control,
                self.realization_profile_ref,
                self.backend_feature_support_refs,
                self.evidence_contract_refs,
                self.tool_affordances,
                self.participant_inject_deliveries,
            )
        ):
            raise ValueError("behavior specifications must aggregate at least one behavior surface reference")
        return self

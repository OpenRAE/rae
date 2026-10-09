"""Authored participant view and observation-boundary models (SEM-210).

Information-boundary classes, view dispositions/transitions, the structural
view rules, and the :class:`ParticipantObservationBoundary` projection with its
cross-rule sequencing invariants.
"""

from enum import Enum

from pydantic import Field, field_validator, model_validator

from .._base import SDLModel


class ParticipantInformationBoundaryClass(str, Enum):
    """SEM-210 classes for participant information-boundary objects."""

    OBSERVABLE_RESOURCE = "observable_resource"
    TELEMETRY_STREAM = "telemetry_stream"
    TOOL_OUTPUT = "tool_output"
    INSTRUCTION = "instruction"
    PUBLIC_TASK_STATEMENT = "public_task_statement"
    STARTER_FILE = "starter_file"
    SCAFFOLD_INSTRUCTION = "scaffold_instruction"
    SUBTASK_GUIDANCE = "subtask_guidance"
    HIDDEN_TRUTH = "hidden_truth"
    PRIVATE_ANSWER_KEY = "private_answer_key"
    CANARY = "canary"
    HOLDOUT_VARIANT = "holdout_variant"
    ADJUDICATION_MATERIAL = "adjudication_material"
    ARCHIVAL_EVIDENCE = "archival_evidence"
    RESOURCE_BUDGET = "resource_budget"


class ParticipantViewDisposition(str, Enum):
    """SEM-210 visibility disposition for one information object."""

    OBSERVABLE = "observable"
    HIDDEN = "hidden"
    EVIDENCE_ONLY = "evidence_only"
    DISCOVERED = "discovered"
    INFERRED = "inferred"
    DISCLOSED = "disclosed"
    CONCEALED = "concealed"
    DECEPTIVE = "deceptive"


class ParticipantViewTransitionKind(str, Enum):
    """SEM-210 state transitions that alter participant visibility over time."""

    DISCOVERY = "discovery"
    INFERENCE = "inference"
    CONCEALMENT = "concealment"
    DISCLOSURE = "disclosure"
    REVOCATION = "revocation"
    DECEPTION = "deception"


class ParticipantViewHistoryEventType(str, Enum):
    """Behavior-history event that realizes a SEM-210 visibility transition."""

    ACTION_ATTEMPTED = "action_attempted"
    STATE_TRANSITION_RECORDED = "state_transition_recorded"
    OBSERVATION_EMITTED = "observation_emitted"
    EPISODE_CLOSE = "episode_close"


_SENSITIVE_BOUNDARY_CLASSES = frozenset(
    {
        ParticipantInformationBoundaryClass.HIDDEN_TRUTH,
        ParticipantInformationBoundaryClass.PRIVATE_ANSWER_KEY,
        ParticipantInformationBoundaryClass.CANARY,
        ParticipantInformationBoundaryClass.HOLDOUT_VARIANT,
        ParticipantInformationBoundaryClass.ADJUDICATION_MATERIAL,
        # A participant resource-budget quota is hidden unless disclosed (SEM-223 EBM-07).
        ParticipantInformationBoundaryClass.RESOURCE_BUDGET,
    }
)

_EXPLICIT_EXPOSURE_DISPOSITIONS = frozenset(
    {
        ParticipantViewDisposition.DISCOVERED,
        ParticipantViewDisposition.INFERRED,
        ParticipantViewDisposition.DISCLOSED,
        ParticipantViewDisposition.DECEPTIVE,
    }
)

_VIEW_TRANSITION_TARGETS = {
    ParticipantViewTransitionKind.DISCOVERY: frozenset({ParticipantViewDisposition.DISCOVERED}),
    ParticipantViewTransitionKind.INFERENCE: frozenset({ParticipantViewDisposition.INFERRED}),
    ParticipantViewTransitionKind.CONCEALMENT: frozenset({ParticipantViewDisposition.CONCEALED}),
    ParticipantViewTransitionKind.DISCLOSURE: frozenset({ParticipantViewDisposition.DISCLOSED}),
    ParticipantViewTransitionKind.REVOCATION: frozenset(
        {ParticipantViewDisposition.HIDDEN, ParticipantViewDisposition.CONCEALED}
    ),
    ParticipantViewTransitionKind.DECEPTION: frozenset({ParticipantViewDisposition.DECEPTIVE}),
}


class ParticipantViewRule(SDLModel):
    """Visibility rule for one participant information-boundary object."""

    information_ref: str
    boundary_class: ParticipantInformationBoundaryClass
    disposition: ParticipantViewDisposition
    visibility_basis: str
    disclosure_rule: str | None = None
    effective_from: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    realized_backend_disclosure: str | None = None
    certainty: str | None = None
    latency_profile: str | None = None

    @field_validator("information_ref", "visibility_basis")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant view rule fields must be non-empty")
        return value

    @field_validator(
        "disclosure_rule",
        "effective_from",
        "realized_backend_disclosure",
        "certainty",
        "latency_profile",
    )
    @classmethod
    def _require_optional_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("participant view rule optional fields must be non-empty when provided")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def _require_non_empty_evidence_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("participant view rule evidence_refs must be non-empty")
        return values

    @model_validator(mode="after")
    def _validate_sem210_exposure_basis(self) -> "ParticipantViewRule":
        if self.disposition == ParticipantViewDisposition.DISCLOSED and not self.disclosure_rule:
            raise ValueError("disclosed view rules require an explicit disclosure_rule")
        if self.boundary_class in _SENSITIVE_BOUNDARY_CLASSES:
            if self.disposition == ParticipantViewDisposition.OBSERVABLE:
                raise ValueError(f"{self.boundary_class.value} must use disposition disclosed, not observable")
            if self.disposition in _EXPLICIT_EXPOSURE_DISPOSITIONS and not self.disclosure_rule:
                raise ValueError(f"{self.boundary_class.value} exposure requires an explicit disclosure_rule")
        if self.disposition == ParticipantViewDisposition.EVIDENCE_ONLY and not self.evidence_refs:
            raise ValueError("evidence_only view rules require evidence_refs")
        return self


class ParticipantViewTransition(SDLModel):
    """Time-indexed SEM-210 transition over a participant view relation."""

    transition_id: str
    transition_kind: ParticipantViewTransitionKind
    information_ref: str
    trigger: str
    effective_from: str
    effective_order: int
    history_event_type: ParticipantViewHistoryEventType
    action_instance_id: str | None = None
    from_disposition: ParticipantViewDisposition
    to_disposition: ParticipantViewDisposition
    disclosure_rule: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    certainty: str
    latency_profile: str
    realized_backend_disclosure: str | None = None

    @field_validator(
        "transition_id",
        "information_ref",
        "trigger",
        "effective_from",
        "action_instance_id",
        "certainty",
        "latency_profile",
    )
    @classmethod
    def _require_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("participant view transition fields must be non-empty")
        return value

    @field_validator("effective_order")
    @classmethod
    def _require_non_negative_effective_order(cls, value: int) -> int:
        if isinstance(value, bool) or value < 0:
            raise ValueError("participant view transition effective_order must be a non-negative integer")
        return value

    @field_validator("disclosure_rule", "realized_backend_disclosure")
    @classmethod
    def _require_optional_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("participant view transition optional fields must be non-empty when provided")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def _require_non_empty_evidence_refs(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("participant view transition evidence_refs must be non-empty")
        return values

    @model_validator(mode="after")
    def _validate_transition_semantics(self) -> "ParticipantViewTransition":
        allowed_targets = _VIEW_TRANSITION_TARGETS[self.transition_kind]
        if self.to_disposition not in allowed_targets:
            allowed = ", ".join(sorted(disposition.value for disposition in allowed_targets))
            raise ValueError(f"{self.transition_kind.value} transitions require to_disposition in: {allowed}")
        if self.from_disposition == self.to_disposition:
            raise ValueError("participant view transitions must alter disposition")
        if self.transition_kind == ParticipantViewTransitionKind.DISCLOSURE and not self.disclosure_rule:
            raise ValueError("disclosure transitions require disclosure_rule")
        if not self.evidence_refs:
            raise ValueError("participant view transitions require evidence_refs")
        if (
            self.history_event_type == ParticipantViewHistoryEventType.EPISODE_CLOSE
            and self.action_instance_id is not None
        ):
            raise ValueError("episode_close visibility transitions must not set action_instance_id")
        if self.history_event_type != ParticipantViewHistoryEventType.EPISODE_CLOSE and self.action_instance_id is None:
            raise ValueError("non-episode-close visibility transitions require action_instance_id")
        return self


def _validate_projection_refs(boundary: "ParticipantObservationBoundary") -> None:
    if not boundary.observable_refs and not boundary.evidence_refs:
        raise ValueError("participant observation boundary requires observable_refs or evidence_refs")
    leaked = sorted(set(boundary.observable_refs) & set(boundary.hidden_refs))
    if leaked:
        joined = ", ".join(leaked)
        raise ValueError(f"hidden_refs must not also be observable_refs; use a disclosed view_rule instead: {joined}")
    evidence_only_refs = {
        rule.information_ref
        for rule in boundary.view_rules
        if rule.disposition == ParticipantViewDisposition.EVIDENCE_ONLY
    }
    observable_evidence_only_refs = sorted(set(boundary.observable_refs) & evidence_only_refs)
    if observable_evidence_only_refs:
        joined = ", ".join(observable_evidence_only_refs)
        raise ValueError(f"evidence_only refs must not also be observable_refs; use evidence_refs instead: {joined}")
    evidence_leaks = sorted((set(boundary.evidence_refs) & set(boundary.hidden_refs)) - evidence_only_refs)
    if evidence_leaks:
        joined = ", ".join(evidence_leaks)
        raise ValueError(f"hidden_refs may only appear in evidence_refs through evidence_only view_rules: {joined}")


def _view_rules_by_ref(view_rules: list[ParticipantViewRule]) -> dict[str, ParticipantViewRule]:
    by_ref: dict[str, ParticipantViewRule] = {}
    duplicate_refs: set[str] = set()
    for rule in view_rules:
        if rule.information_ref in by_ref:
            duplicate_refs.add(rule.information_ref)
        by_ref[rule.information_ref] = rule
    if duplicate_refs:
        joined = ", ".join(sorted(duplicate_refs))
        raise ValueError(f"view_rules require unique information_ref values: {joined}")
    return by_ref


def _transition_kinds_by_ref(
    view_transitions: list[ParticipantViewTransition],
) -> dict[str, set[ParticipantViewTransitionKind]]:
    transition_ids: set[str] = set()
    duplicate_transition_ids: set[str] = set()
    effective_orders: set[int] = set()
    duplicate_effective_orders: set[int] = set()
    by_ref: dict[str, set[ParticipantViewTransitionKind]] = {}
    for transition in view_transitions:
        if transition.transition_id in transition_ids:
            duplicate_transition_ids.add(transition.transition_id)
        transition_ids.add(transition.transition_id)
        if transition.effective_order in effective_orders:
            duplicate_effective_orders.add(transition.effective_order)
        effective_orders.add(transition.effective_order)
        by_ref.setdefault(transition.information_ref, set()).add(transition.transition_kind)
    if duplicate_transition_ids:
        joined = ", ".join(sorted(duplicate_transition_ids))
        raise ValueError(f"view_transitions require unique transition_id values: {joined}")
    if duplicate_effective_orders:
        joined = ", ".join(str(order) for order in sorted(duplicate_effective_orders))
        raise ValueError(f"view_transitions require unique effective_order values: {joined}")
    return by_ref


def _validate_transitions_have_view_rules(
    *,
    view_transitions: list[ParticipantViewTransition],
    view_rules_by_ref: dict[str, ParticipantViewRule],
) -> None:
    transitions_without_rules = sorted(
        transition.transition_id
        for transition in view_transitions
        if transition.information_ref not in view_rules_by_ref
    )
    if transitions_without_rules:
        joined = ", ".join(transitions_without_rules)
        raise ValueError(f"view_transitions require matching view_rules: {joined}")


def _validate_sensitive_transition_disclosures(
    *,
    view_transitions: list[ParticipantViewTransition],
    view_rules_by_ref: dict[str, ParticipantViewRule],
) -> None:
    for transition in view_transitions:
        rule = view_rules_by_ref.get(transition.information_ref)
        if not rule or rule.boundary_class not in _SENSITIVE_BOUNDARY_CLASSES:
            continue
        if transition.to_disposition not in _EXPLICIT_EXPOSURE_DISPOSITIONS or transition.disclosure_rule:
            continue
        raise ValueError(
            f"{transition.transition_kind.value} transitions exposing "
            f"{rule.boundary_class.value} require disclosure_rule"
        )


def _initial_view_relation(
    *,
    view_rules: list[ParticipantViewRule],
) -> dict[str, ParticipantViewDisposition]:
    return {rule.information_ref: rule.disposition for rule in view_rules}


def _validate_view_transition_sequence(
    *,
    view_rules: list[ParticipantViewRule],
    view_transitions: list[ParticipantViewTransition],
) -> None:
    relation = _initial_view_relation(view_rules=view_rules)
    for transition in sorted(view_transitions, key=lambda item: item.effective_order):
        if relation[transition.information_ref] != transition.from_disposition:
            raise ValueError(
                f"view_transition '{transition.transition_id}' from_disposition "
                f"does not match current disposition for {transition.information_ref}"
            )
        if relation.get(transition.information_ref) == transition.to_disposition:
            raise ValueError(
                f"view_transition '{transition.transition_id}' does not alter disposition for "
                f"{transition.information_ref}"
            )
        relation[transition.information_ref] = transition.to_disposition


class ParticipantObservationBoundary(SDLModel):
    """Participant-specific observation projection boundary."""

    projection_basis: str
    observable_refs: list[str] = Field(default_factory=list)
    hidden_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    redaction_policy: str
    latency_profile: str
    observer_effects: list[str] = Field(default_factory=list)
    view_rules: list[ParticipantViewRule] = Field(default_factory=list)
    view_transitions: list[ParticipantViewTransition] = Field(default_factory=list)
    realized_view_disclosure: str | None = None

    @field_validator("projection_basis", "redaction_policy", "latency_profile")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant observation boundary fields must be non-empty")
        return value

    @field_validator("realized_view_disclosure")
    @classmethod
    def _require_optional_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("realized_view_disclosure must be non-empty when provided")
        return value

    @model_validator(mode="after")
    def _validate_projection(self) -> "ParticipantObservationBoundary":
        _validate_projection_refs(self)
        view_rules_by_ref = _view_rules_by_ref(self.view_rules)
        _transition_kinds_by_ref(self.view_transitions)
        _validate_transitions_have_view_rules(
            view_transitions=self.view_transitions,
            view_rules_by_ref=view_rules_by_ref,
        )
        _validate_sensitive_transition_disclosures(
            view_transitions=self.view_transitions,
            view_rules_by_ref=view_rules_by_ref,
        )
        _validate_view_transition_sequence(
            view_rules=self.view_rules,
            view_transitions=self.view_transitions,
        )
        return self

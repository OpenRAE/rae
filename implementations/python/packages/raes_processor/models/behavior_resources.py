"""Participant-behavior and workflow resource records plus shared validation helpers."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from raes.semantics.workflow import WorkflowStepSemanticContract
from raes_backend_protocols.capabilities import WorkflowFeature, WorkflowStatePredicateFeature
from raes_contracts.participant_behavior import ParticipantObservationStatus
from raes_contracts.versions import WORKFLOW_STATE_SCHEMA_VERSION
from raes_contracts.workflow import WorkflowExecutionContract, WorkflowResultContract, WorkflowStepOutcome

from .participant_resources import (
    ParticipantResourceDemandRuntime,
    ParticipantResourceFairnessRuntime,
    ParticipantResourceOwnerRuntime,
)
from .resources import ResolvedResource


@dataclass(frozen=True)
class ParticipantObservationBoundaryRuntime(ResolvedResource):
    """Compiled participant observation projection boundary."""

    boundary_name: str = ""
    projection_basis: str = ""
    hidden_refs: tuple[str, ...] = ()
    observable_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    disclosed_refs: tuple[str, ...] = ()
    evidence_only_refs: tuple[str, ...] = ()
    discovered_refs: tuple[str, ...] = ()
    inferred_refs: tuple[str, ...] = ()
    concealed_refs: tuple[str, ...] = ()
    deceptive_refs: tuple[str, ...] = ()
    view_transitions: tuple[dict[str, Any], ...] = ()
    view_relation_timeline: tuple[dict[str, Any], ...] = ()
    realized_view_disclosure: str = ""


@dataclass(frozen=True)
class ParticipantOutcomeInterpretationRuleRuntime(ResolvedResource):
    """Compiled SEM-215 participant outcome interpretation rule."""

    rule_name: str = ""
    semantic_version: str = ""
    participant_scope: str = ""
    observation_point_basis: str = ""
    interpretation_basis: str = ""
    source_layers: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    target_layers: tuple[str, ...] = ()
    target_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParticipantInteractiveAccessRuntime:
    """Resolved authored interactive access carried with one participant."""

    access_id: str
    target_ref: str
    target_address: str
    channel: str
    account_ref: str = ""
    account_address: str = ""


@dataclass(frozen=True)
class ParticipantBehaviorRuntime(ResolvedResource):
    """Compiled role-neutral participant behavior binding."""

    participant_name: str = ""
    entity_name: str = ""
    starting_account_refs: tuple[str, ...] = ()
    starting_account_addresses: tuple[str, ...] = ()
    initial_knowledge_addresses: tuple[str, ...] = ()
    starting_assertion_refs: tuple[str, ...] = ()
    starting_assertion_addresses: tuple[str, ...] = ()
    authority_anchor_refs: tuple[str, ...] = ()
    authority_anchor_addresses: tuple[str, ...] = ()
    operating_scope_refs: tuple[str, ...] = ()
    operating_scope_addresses: tuple[str, ...] = ()
    action_contract_addresses: tuple[str, ...] = ()
    observation_boundary_addresses: tuple[str, ...] = ()
    interactive_access: tuple[ParticipantInteractiveAccessRuntime, ...] = ()
    interpretation_mode: str = "role-neutral-projection"


@dataclass(frozen=True)
class ParticipantExecutionBindingRuntime:
    """Compiled action-to-target relation for native participant execution."""

    action_contract_address: str
    target_addresses: tuple[str, ...]
    participant_implementation_ref: str
    max_action_attempts: int
    max_in_flight: int
    interaction_classes: tuple[str, ...] = ()
    shared_state_refs: tuple[str, ...] = ()
    related_action_contract_addresses: tuple[str, ...] = ()
    commutative_shared_state_refs: tuple[str, ...] = ()
    commutative_related_action_contract_addresses: tuple[str, ...] = ()
    merge_rule_refs: tuple[str, ...] = ()
    shared_state_merge_rules: tuple[tuple[str, str], ...] = ()
    related_action_merge_rules: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ParticipantAutonomousExecutionRuntime(ResolvedResource):
    """Compiled deterministic execution policy for ordinary participants."""

    behavior_specification_address: str = ""
    participant_addresses: tuple[str, ...] = ()
    participant_implementation_ref: str = ""
    clock_address: str = ""
    progression_policy_address: str = ""
    temporal_constraint_addresses: tuple[str, ...] = ()
    action_contract_addresses: tuple[str, ...] = ()
    target_addresses: tuple[str, ...] = ()
    execution_bindings: tuple[ParticipantExecutionBindingRuntime, ...] = ()
    observation_boundary_address: str = ""
    selection_strategy: str = ""
    max_action_attempts: int = 0
    max_in_flight: int = 0
    failure_policy: str = ""
    evaluation_authority_mode: str = ""
    objective_refs: tuple[str, ...] = ()
    proof_producer_refs: tuple[str, ...] = ()
    score_authority_refs: tuple[str, ...] = ()
    receipt_authority_refs: tuple[str, ...] = ()
    profile: str = "participant-autonomous-execution/v1"
    work_window_addresses: tuple[str, ...] = ()
    pause_window_addresses: tuple[str, ...] = ()
    stochastic_control_ref: str = ""
    timing_minimum_ticks: int = 0
    timing_maximum_ticks: int = 0
    outside_window_disposition: str = ""
    empty_eligible_disposition: str = ""
    action_candidate_ids: tuple[str, ...] = ()
    action_candidate_weights: tuple[int, ...] = ()
    action_candidate_dependencies: tuple[tuple[str, ...], ...] = ()
    action_candidate_retry_failure_classes: tuple[tuple[str, ...], ...] = ()
    action_candidate_max_retries: tuple[int, ...] = ()
    action_candidate_cooldown_ticks: tuple[int, ...] = ()
    max_occurrences: int = 0
    max_burst_size: int = 1
    resource_owners: tuple[ParticipantResourceOwnerRuntime, ...] = ()
    resource_demands: tuple[ParticipantResourceDemandRuntime, ...] = ()
    resource_fairness: ParticipantResourceFairnessRuntime = field(default_factory=ParticipantResourceFairnessRuntime)


@dataclass(frozen=True)
class MixedControlDispositionRulesRuntime:
    """Compiled fail-closed decision disposition rules."""

    duplicate: str
    stale: str
    revoked: str
    late: str
    concurrent: str
    conflict: str


@dataclass(frozen=True)
class MixedControlControllerStateRuntime(ResolvedResource):
    """Compiled controller binding nested under one behavior specification."""

    state_id: str = ""
    controller_ref: str = ""
    controller_address: str = ""
    authority_basis_refs: tuple[str, ...] = ()
    authority_basis_addresses: tuple[str, ...] = ()
    scope_refs: tuple[str, ...] = ()
    scope_addresses: tuple[str, ...] = ()
    policy_revision: str = ""
    valid_from_order: int = 0
    valid_until_order: int = 0
    authority_status: str = ""
    evidence_refs: tuple[str, ...] = ()
    evidence_addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class MixedControlTransitionRuntime(ResolvedResource):
    """Compiled ordered control transition nested under one behavior specification."""

    transition_id: str = ""
    transition_kind: str = ""
    from_state_address: str = ""
    to_state_address: str = ""
    policy_revision: str = ""
    expected_state_revision: int = 0
    resulting_state_revision: int = 0
    effective_order: int = 0
    valid_from_order: int = 0
    valid_until_order: int = 0
    proposal_address: str = ""
    proposal_revision: int | None = None
    evidence_refs: tuple[str, ...] = ()
    evidence_addresses: tuple[str, ...] = ()
    completion_evidence_refs: tuple[str, ...] = ()
    completion_evidence_addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParticipantBehaviorSpecificationRuntime(ResolvedResource):
    """Compiled first-class participant behavior specification aggregate."""

    spec_name: str = ""
    semantic_version: str = ""
    lifecycle_state: str = ""
    participant_addresses: tuple[str, ...] = ()
    participant_role_refs: tuple[str, ...] = ()
    action_contract_addresses: tuple[str, ...] = ()
    observation_boundary_addresses: tuple[str, ...] = ()
    outcome_interpretation_rule_addresses: tuple[str, ...] = ()
    authority_scope_refs: tuple[str, ...] = ()
    authority_scope_addresses: tuple[str, ...] = ()
    behavior_mode: str = ""
    autonomous_execution: ParticipantAutonomousExecutionRuntime | None = None
    mixed_control_participant_address: str = ""
    mixed_control_policy_revision: str = ""
    mixed_control_order_strategy: str = ""
    mixed_control_initial_state_address: str = ""
    mixed_control_dispositions: MixedControlDispositionRulesRuntime | None = None
    controller_states: tuple[MixedControlControllerStateRuntime, ...] = ()
    control_transitions: tuple[MixedControlTransitionRuntime, ...] = ()
    realization_profile_ref: str = ""
    backend_feature_support_refs: tuple[str, ...] = ()
    evidence_contract_refs: tuple[str, ...] = ()
    tool_affordance_addresses: tuple[str, ...] = ()
    participant_inject_delivery_addresses: tuple[str, ...] = ()
    extension_policy: str = ""
    extension_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParticipantToolAffordanceRuntime(ResolvedResource):
    """Compiled semantic IR for one authored participant tool-affordance binding."""

    affordance_id: str = ""
    behavior_specification_address: str = ""
    tool_ref: str = ""
    tool_address: str = ""
    action_contract_refs: tuple[str, ...] = ()
    action_contract_addresses: tuple[str, ...] = ()
    observation_boundary_refs: tuple[str, ...] = ()
    observation_boundary_addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParticipantInjectDeliveryRuntime(ResolvedResource):
    """Compiled declaration of participant delivery intent, never realization."""

    binding_id: str = ""
    behavior_specification_address: str = ""
    participant_address: str = ""
    inject_address: str = ""
    event_address: str = ""
    script_address: str = ""
    story_address: str = ""
    source_item_ref: str = ""
    source_item_address: str = ""
    result_item_ref: str = ""
    result_item_address: str = ""
    observation_boundary_address: str = ""
    delivery_kind: str = ""
    policy_ref: str = ""
    policy_revision: str = ""
    exposure_policy_ref: str = ""
    audience_scope_ref: str = ""
    visibility_basis_ref: str = ""
    disclosure_basis_ref: str = ""
    order_basis: str = ""
    temporal_constraint_addresses: tuple[str, ...] = ()
    evidence_requirement_addresses: tuple[str, ...] = ()
    failure_disposition: str = ""
    control_transition_address: str = ""
    controller_address: str = ""
    control_authority_scope_refs: tuple[str, ...] = ()
    control_authority_scope_addresses: tuple[str, ...] = ()
    control_effective_order: int | None = None
    control_valid_from_order: int | None = None
    control_valid_until_order: int | None = None
    control_evidence_refs: tuple[str, ...] = ()
    control_evidence_addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventRuntime(ResolvedResource):
    """Resolved orchestration event."""

    assertion_names: tuple[str, ...] = ()
    assertion_addresses: tuple[str, ...] = ()
    inject_names: tuple[str, ...] = ()
    inject_addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScriptRuntime(ResolvedResource):
    """Resolved script with event dependencies."""

    event_addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoryRuntime(ResolvedResource):
    """Resolved story with script dependencies."""

    script_addresses: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObjectiveWindowReferenceRuntime:
    """Normalized resolved objective/window reference."""

    raw: str
    canonical_name: str
    reference_kind: str
    dependency_roles: tuple[str, ...] = ()
    workflow_name: str = ""
    step_name: str = ""
    namespace_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowStepStatePredicateRuntime:
    """Resolved predicate clause over prior workflow step state."""

    step_name: str
    outcomes: tuple[WorkflowStepOutcome, ...] = ()
    min_attempts: int | str | None = None


@dataclass(frozen=True)
class WorkflowPredicateRuntime:
    """Resolved workflow predicate semantics."""

    assertion_addresses: tuple[str, ...] = ()
    objective_addresses: tuple[str, ...] = ()
    step_state_predicates: tuple[WorkflowStepStatePredicateRuntime, ...] = ()

    @property
    def external_addresses(self) -> tuple[str, ...]:
        seen: set[str] = set()
        ordered: list[str] = []
        for address in (
            *self.assertion_addresses,
            *self.objective_addresses,
        ):
            if address in seen:
                continue
            seen.add(address)
            ordered.append(address)
        return tuple(ordered)


@dataclass(frozen=True)
class WorkflowSwitchCaseRuntime:
    """Resolved ordered switch-case branch semantics."""

    case_index: int
    predicate: WorkflowPredicateRuntime
    next_step: str


@dataclass(frozen=True)
class WorkflowStepRuntime:
    """Resolved workflow step semantics."""

    name: str
    step_type: str
    execution_mode: str = "scripted"
    objective_address: str = ""
    procedure_ref: str = ""
    scaffold_refs: tuple[str, ...] = ()
    allowed_action_families: tuple[str, ...] = ()
    tool_affordance_refs: tuple[str, ...] = ()
    capability_refs: tuple[str, ...] = ()
    fact_binding_refs: tuple[str, ...] = ()
    predicate: WorkflowPredicateRuntime | None = None
    next_step: str = ""
    on_success: str = ""
    on_failure: str = ""
    on_exhausted: str = ""
    then_step: str = ""
    else_step: str = ""
    switch_cases: tuple[WorkflowSwitchCaseRuntime, ...] = ()
    default_step: str = ""
    branches: tuple[str, ...] = ()
    join_step: str = ""
    owning_parallel_step: str = ""
    called_workflow_address: str = ""
    compensation_workflow_address: str = ""
    max_attempts: int | str | None = None
    state_contract: WorkflowStepSemanticContract = field(
        default_factory=lambda: WorkflowStepSemanticContract(step_type="")
    )


@dataclass(frozen=True)
class WorkflowRuntime(ResolvedResource):
    """Resolved workflow control program."""

    start_step: str = ""
    referenced_objective_addresses: tuple[str, ...] = ()
    control_steps: dict[str, WorkflowStepRuntime] = field(default_factory=dict)
    control_edges: dict[str, tuple[str, ...]] = field(default_factory=dict)
    join_owners: dict[str, str] = field(default_factory=dict)
    step_assertion_addresses: dict[str, tuple[str, ...]] = field(default_factory=dict)
    step_predicate_addresses: dict[str, tuple[str, ...]] = field(default_factory=dict)
    required_features: tuple[WorkflowFeature, ...] = ()
    required_state_predicate_features: tuple[WorkflowStatePredicateFeature, ...] = ()
    result_contract: "WorkflowResultContract" = field(default_factory=lambda: WorkflowResultContract())
    execution_contract: "WorkflowExecutionContract" = field(default_factory=lambda: WorkflowExecutionContract())
    state_schema_version: str = WORKFLOW_STATE_SCHEMA_VERSION


def _participant_observation_status_from_payload(value: object) -> ParticipantObservationStatus | None:
    if isinstance(value, ParticipantObservationStatus):
        return value
    if value is None:
        return None
    return ParticipantObservationStatus(str(value))


def _validate_required_string(value: object, message: str) -> None:
    if not isinstance(value, str) or not value:
        raise TypeError(message)


def _validate_optional_string(value: object, message: str) -> None:
    if value is not None and (not isinstance(value, str) or not value):
        raise TypeError(message)


def _validate_optional_address(value: str | None, *, prefix: str, message: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.startswith(prefix)):
        raise ValueError(message)


def _validate_required_address(value: str, *, prefix: str, message: str) -> None:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError(message)


def _tuple_of_non_empty_strings(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be a list of strings")
    values = tuple(value)
    refs = tuple(str(item) for item in values if isinstance(item, str) and item)
    if len(refs) != len(values):
        raise TypeError(f"{field_name} entries must be non-empty strings")
    if len(set(refs)) != len(refs):
        raise ValueError(f"{field_name} entries must be unique")
    return refs


def _observation_point_matches_action_instance(observation_point: str, action_instance_id: str) -> bool:
    return action_instance_id in observation_point.split(":")


def _optional_payload_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None


_PARTICIPANT_TERMINAL_OBSERVATION_STATUSES = frozenset(
    {
        ParticipantObservationStatus.TERMINAL,
        ParticipantObservationStatus.ORPHANED_ACTION,
    }
)
_PARTICIPANT_VISIBLE_VIEW_DISPOSITIONS = frozenset({"observable", "discovered", "inferred", "disclosed", "deceptive"})
_PARTICIPANT_OBSERVATION_DETAIL_REF_KEYS = ("visible_refs", "disclosed_refs", "evidence_refs")
_PARTICIPANT_OBSERVATION_DETAIL_KEYS = frozenset(_PARTICIPANT_OBSERVATION_DETAIL_REF_KEYS)

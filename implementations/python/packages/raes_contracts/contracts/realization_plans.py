"""Realization plan, snapshot, and operation-receipt contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance

from ..addressing import CompiledAddress
from ..artifact_requirements import ArtifactSatisfactionDisclosureModel
from ..bounded_domains import DomainDescriptor
from ..compute_substrate import validate_compute_substrate_constraint
from ..observation_demand import EffectiveObservationDemand
from ..planning import (
    RealizationAuthorityMode,
    RealizationResolutionSource,
    RuntimeDomain,
    require_plan_operation_identity,
)
from ..realization_structure import RealizationStructure
from ..versions import RUNTIME_SNAPSHOT_SCHEMA_VERSION
from ..vocabulary import ObservationStrength, RealizationVerificationScope
from .base import ContractModel, NonEmptyString
from .execution_state import (
    EvaluationHistoryEventModel,
    EvaluationResultStateModel,
    PropositionTruthResultModel,
    WorkflowExecutionStateModel,
    WorkflowHistoryEventModel,
)
from .operating_systems import ObservedOperatingSystemIdentityModel
from .participant_control import ParticipantControlOccurrenceModel
from .participant_crossing import ParticipantCrossingOccurrenceModel
from .participant_envelopes import (
    ParticipantJointActionRecordModel,
    ParticipantSharedStateRecordModel,
    ParticipantTimeManagementContextModel,
)
from .participant_execution import ParticipantExecutionServiceStateModel
from .participant_information_state import ParticipantInformationStateRecordModel
from .participant_resource_budgets import (
    ParticipantResourceBudgetEventModel,
    ParticipantResourceBudgetStateModel,
    ParticipantResourcePoolStateModel,
)
from .participant_runtime import (
    ParticipantAutonomousExecutionStateModel,
    ParticipantBehaviorHistoryEventModel,
    ParticipantEpisodeHistoryEventModel,
    ParticipantEpisodeStateModel,
)
from .realization_observation_validation import validate_realization_observation_disclosure
from .time_model import TimeRuntimeStateModel


class PlanOperationModel(ContractModel):
    action: str
    address: CompiledAddress
    resource_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ordering_dependencies: list[CompiledAddress] = Field(default_factory=list)
    refresh_dependencies: list[CompiledAddress] = Field(default_factory=list)


def _require_unique_operation_addresses(operations: list[PlanOperationModel]) -> None:
    addresses = [operation.address for operation in operations]
    if len(addresses) != len(set(addresses)):
        raise ValueError("Plan operation addresses must be unique")


def _require_operation_identities(operations: list[PlanOperationModel], domain: RuntimeDomain) -> None:
    for operation in operations:
        require_plan_operation_identity(domain, operation.address, operation.resource_type)


def _require_startup_order_addresses(
    operations: list[PlanOperationModel],
    startup_order: list[str],
) -> None:
    if len(startup_order) != len(set(startup_order)):
        raise ValueError("Plan startup_order addresses must be unique")
    operation_addresses = {operation.address for operation in operations}
    unknown = set(startup_order) - operation_addresses
    if unknown:
        raise ValueError("Plan startup_order must reference admitted operation addresses")


class RealizationEnvelopeIdentityModel(ContractModel):
    """Immutable realization-envelope identity carried across runtime contracts."""

    contract_id: Literal["realization-envelope-v1"] = "realization-envelope-v1"
    envelope_id: NonEmptyString
    schema_version: Literal["realization-envelope/v1"] = "realization-envelope/v1"
    digest: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    configuration_digest: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


class PlannedRealizationConstraintModel(ContractModel):
    """Published author realization demand on a provisioning plan."""

    address: CompiledAddress
    field_path: NonEmptyString
    concern: Literal["compute-substrate"]
    posture: Literal["open", "constrained", "exact"]
    value_domain: DomainDescriptor | None = None
    governing_scope: NonEmptyString
    provenance: Literal["author-declared", "legacy-node-type-vm"]

    @model_validator(mode="after")
    def _validate_domain(self) -> PlannedRealizationConstraintModel:
        validate_compute_substrate_constraint(self.posture, self.value_domain)
        return self


class RealizationAuthorityBoundModel(ContractModel):
    """One safe typed domain over a resolved concern value or owned leaf."""

    value_pointer: Annotated[str, Field(pattern=r"^(?:/(?:[^~/]|~[01])*)*$")]
    domain: DomainDescriptor
    identity_digest: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")] | None = None


class ResolvedRealizationAuthorityModel(ContractModel):
    """Published value-free realization authority for one plan concern."""

    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"mode": {"const": "constrained"}}, "required": ["mode"]},
                    "then": {
                        "properties": {"bounds": {"minItems": 1}},
                        "required": ["bounds"],
                    },
                },
                {
                    "if": {
                        "properties": {"mode": {"enum": ["closed", "open", "exact"]}},
                        "required": ["mode"],
                    },
                    "then": {"properties": {"bounds": {"maxItems": 0}}},
                },
                {
                    "if": {
                        "properties": {"source": {"const": "legacy-default"}},
                        "required": ["source"],
                    },
                    "then": {"properties": {"mode": {"const": "closed"}}},
                },
                {
                    "if": {
                        "properties": {"source": {"const": "apparatus-default"}},
                        "required": ["source"],
                    },
                    "then": {"properties": {"mode": {"enum": ["closed", "open"]}}},
                },
            ]
        }
    )

    address: CompiledAddress
    field_path: NonEmptyString
    domain: NonEmptyString
    requirement_kind: NonEmptyString
    payload_pointer: Annotated[str, Field(pattern=r"^/(?:[^~/]|~[01])*(?:/(?:[^~/]|~[01])*)*$")]
    mode: RealizationAuthorityMode
    source: RealizationResolutionSource
    provenance: ExplicitnessProvenance = ExplicitnessProvenance.AUTHOR_DECLARED
    governing_scope: NonEmptyString | None = None
    bounds: list[RealizationAuthorityBoundModel] = Field(default_factory=list)
    verification_scope: RealizationVerificationScope | None = None
    required_observation_strength: ObservationStrength | None = None
    structure: RealizationStructure | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def _validate_mode_bounds(self) -> ResolvedRealizationAuthorityModel:
        if self.mode is RealizationAuthorityMode.CONSTRAINED and not self.bounds:
            raise ValueError("constrained realization authority requires typed bounds")
        if self.mode is not RealizationAuthorityMode.CONSTRAINED and self.bounds:
            raise ValueError("only constrained realization authority may carry typed bounds")
        if (
            self.source is RealizationResolutionSource.LEGACY_DEFAULT
            and self.mode is not RealizationAuthorityMode.CLOSED
        ):
            raise ValueError("legacy realization default must resolve closed")
        if self.source is RealizationResolutionSource.APPARATUS_DEFAULT and self.mode not in {
            RealizationAuthorityMode.CLOSED,
            RealizationAuthorityMode.OPEN,
        }:
            raise ValueError("apparatus realization default must resolve open or closed")
        bound_keys = [(bound.identity_digest, bound.value_pointer) for bound in self.bounds]
        if len(bound_keys) != len(set(bound_keys)):
            raise ValueError("realization authority bounds must identify unique value leaves")
        return self


class ProvisioningPlanModel(ContractModel):
    operations: list[PlanOperationModel] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    realization_authority: list[ResolvedRealizationAuthorityModel]
    realization_envelope: RealizationEnvelopeIdentityModel | None = None
    realization_constraints: list[PlannedRealizationConstraintModel] = Field(default_factory=list)
    operation_id: NonEmptyString | None = None
    observation_demands: list[EffectiveObservationDemand] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_operation_addresses(self) -> ProvisioningPlanModel:
        _require_unique_operation_addresses(self.operations)
        _require_operation_identities(self.operations, RuntimeDomain.PROVISIONING)
        identities = [(item.address, item.concern) for item in self.realization_constraints]
        if len(identities) != len(set(identities)):
            raise ValueError("Provisioning plan realization constraints must identify unique concerns")
        authority_keys = [(entry.address, entry.requirement_kind) for entry in self.realization_authority]
        if len(authority_keys) != len(set(authority_keys)):
            raise ValueError("Provisioning plan realization authority must identify unique concerns")
        pointer_keys = [(entry.address, entry.payload_pointer) for entry in self.realization_authority]
        if len(pointer_keys) != len(set(pointer_keys)):
            raise ValueError("Provisioning plan realization authority payload pointers must be unique per resource")
        admitted_addresses = {operation.address for operation in self.operations if operation.action != "delete"}
        if {entry.address for entry in self.realization_authority} - admitted_addresses:
            raise ValueError("Provisioning plan realization authority must reference non-delete operations")
        return self


class OrchestrationPlanModel(ContractModel):
    operations: list[PlanOperationModel] = Field(default_factory=list)
    startup_order: list[CompiledAddress] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    observation_demands: list[EffectiveObservationDemand] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_operation_addresses(self) -> OrchestrationPlanModel:
        _require_unique_operation_addresses(self.operations)
        _require_operation_identities(self.operations, RuntimeDomain.ORCHESTRATION)
        _require_startup_order_addresses(self.operations, self.startup_order)
        return self


class EvaluationPlanModel(ContractModel):
    operations: list[PlanOperationModel] = Field(default_factory=list)
    startup_order: list[CompiledAddress] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    observation_demands: list[EffectiveObservationDemand] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_operation_addresses(self) -> EvaluationPlanModel:
        _require_unique_operation_addresses(self.operations)
        _require_operation_identities(self.operations, RuntimeDomain.EVALUATION)
        _require_startup_order_addresses(self.operations, self.startup_order)
        return self


class SnapshotEntryModel(ContractModel):
    address: CompiledAddress
    domain: str
    resource_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ordering_dependencies: list[CompiledAddress] = Field(default_factory=list)
    refresh_dependencies: list[CompiledAddress] = Field(default_factory=list)
    status: str = "ready"


class RealizationProvenanceEntryModel(ContractModel):
    """SEM-218 invariant I5: provenance for one realized realization concern.

    Distinguishes ``author-declared`` / ``processor-derived`` / ``backend-realized``
    origins for a realized concern recorded on the snapshot's result / history
    surfaces. Carries field-path and kind references only (never the realized
    value, per the SEM-218 host-exposure gate). Kept distinct from ADR-054
    lifecycle ``phase_realization`` and API-407 participant feature support.
    """

    address: NonEmptyString
    field_path: NonEmptyString
    domain: NonEmptyString
    requirement_kind: NonEmptyString
    explicitness: ExplicitnessClass
    provenance: ExplicitnessProvenance
    governing_scope: NonEmptyString | None = None
    artifact_satisfaction: ArtifactSatisfactionDisclosureModel | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class RealizationObservationDisclosureModel(ContractModel):
    """Corroboration metadata, with governed substrate evidence when applicable."""

    address: CompiledAddress
    field_path: NonEmptyString
    domain: NonEmptyString
    requirement_kind: NonEmptyString
    verification_scope: RealizationVerificationScope
    observation_strength: ObservationStrength = Field(json_schema_extra={"not": {"const": "none"}})
    observed_value: NonEmptyString | None = None
    operating_system: ObservedOperatingSystemIdentityModel | None = None
    operation_id: NonEmptyString | None = None
    envelope_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    configuration_digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    observer_version: NonEmptyString | None = None
    sequence: int | None = Field(default=None, ge=0)
    binding_verified: bool = False

    @model_validator(mode="after")
    def _require_evidence(self) -> RealizationObservationDisclosureModel:
        validate_realization_observation_disclosure(self)
        return self


def _require_embedded_map_keys(
    values: Mapping[str, object],
    attribute: str,
    message: str,
) -> None:
    for map_key, value in values.items():
        if map_key != getattr(value, attribute):
            raise ValueError(message)


def _validate_execution_service_budget_projection(
    services: Mapping[str, ParticipantExecutionServiceStateModel],
    budget_states: Mapping[str, ParticipantResourceBudgetStateModel],
) -> None:
    budget_refs = set(budget_states)
    for service in services.values():
        missing = sorted(set(service.resource_budget_state_refs) - budget_refs)
        if missing:
            raise ValueError(
                "Participant execution service references missing resource-budget states: " + ", ".join(missing)
            )
        concurrency = [
            budget_states[budget_ref]
            for budget_ref in service.resource_budget_state_refs
            if budget_states[budget_ref].resource_kind == "concurrent_actions"
        ]
        if not concurrency:
            continue
        if len(concurrency) != 1:
            raise ValueError(
                "Participant execution service must reference exactly one authoritative concurrency budget"
            )
        authoritative = concurrency[0]
        projection = (service.capacity, service.reserved, service.in_flight)
        authority = (authoritative.limit, authoritative.reserved, authoritative.current_use)
        if projection != authority:
            raise ValueError(
                "Participant execution service concurrency projection must "
                "equal its authoritative resource-budget state"
            )


class RuntimeSnapshotEnvelopeModel(ContractModel):
    """Published envelope for a live runtime snapshot.

    Participant episode surfaces (``participant_episode_results`` and
    ``participant_episode_history``) are both keyed by the stable
    ``participant_address`` of the participant the state/history belongs
    to. SEM-208 participant behavior history is keyed the same way and
    records action, observation, and state-transition events with compiled
    behavior-contract addresses. The episode results map carries the
    currently-live episode state per participant; prior episodes survive only
    through append-only history streams and the ``previous_episode_id`` chain
    on each state.
    """

    schema_version: Literal[RUNTIME_SNAPSHOT_SCHEMA_VERSION] = RUNTIME_SNAPSHOT_SCHEMA_VERSION
    entries: dict[CompiledAddress, SnapshotEntryModel] = Field(default_factory=dict)
    orchestration_results: dict[str, WorkflowExecutionStateModel] = Field(default_factory=dict)
    orchestration_history: dict[str, list[WorkflowHistoryEventModel]] = Field(default_factory=dict)
    evaluation_results: dict[str, EvaluationResultStateModel] = Field(default_factory=dict)
    evaluation_history: dict[str, list[EvaluationHistoryEventModel]] = Field(default_factory=dict)
    proposition_truth_results: dict[str, PropositionTruthResultModel] = Field(default_factory=dict)
    participant_episode_results: dict[str, ParticipantEpisodeStateModel] = Field(default_factory=dict)
    participant_episode_history: dict[str, list[ParticipantEpisodeHistoryEventModel]] = Field(default_factory=dict)
    participant_episode_closure_records: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    participant_behavior_history: dict[str, list[ParticipantBehaviorHistoryEventModel]] = Field(default_factory=dict)
    participant_control_history: dict[str, list[ParticipantControlOccurrenceModel]] = Field(default_factory=dict)
    participant_crossing_history: dict[str, list[ParticipantCrossingOccurrenceModel]] = Field(default_factory=dict)
    information_state_history: dict[str, list[ParticipantInformationStateRecordModel]] = Field(default_factory=dict)
    participant_autonomous_execution_states: dict[str, ParticipantAutonomousExecutionStateModel] = Field(
        default_factory=dict
    )
    participant_execution_services: dict[str, ParticipantExecutionServiceStateModel] = Field(default_factory=dict)
    participant_resource_budget_states: dict[str, ParticipantResourceBudgetStateModel] = Field(default_factory=dict)
    participant_resource_pool_states: dict[str, ParticipantResourcePoolStateModel] = Field(default_factory=dict)
    participant_resource_budget_events: dict[str, ParticipantResourceBudgetEventModel] = Field(default_factory=dict)
    shared_state_records: dict[str, ParticipantSharedStateRecordModel] = Field(default_factory=dict)
    shared_state_history: dict[str, list[ParticipantSharedStateRecordModel]] = Field(default_factory=dict)
    joint_action_records: dict[str, ParticipantJointActionRecordModel] = Field(default_factory=dict)
    time_management_contexts: dict[str, ParticipantTimeManagementContextModel] = Field(default_factory=dict)
    time_model_state: TimeRuntimeStateModel | None = None
    realization_provenance: list[RealizationProvenanceEntryModel] = Field(default_factory=list)
    realization_observations: list[RealizationObservationDisclosureModel] = Field(default_factory=list)
    realization_envelope: RealizationEnvelopeIdentityModel | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_entry_addresses(self) -> RuntimeSnapshotEnvelopeModel:
        _require_embedded_map_keys(
            self.entries,
            "address",
            "Runtime snapshot entries map key must equal embedded address",
        )
        for map_key, state in self.participant_autonomous_execution_states.items():
            expected = f"{state.policy_address}.state.{state.participant_address}"
            if map_key != expected:
                raise ValueError(
                    "Autonomous participant state map key must equal the embedded policy and participant address"
                )
        key_checks = (
            (
                self.participant_execution_services,
                "execution_scope_ref",
                "Participant execution service map key must equal execution_scope_ref",
            ),
            (
                self.participant_resource_budget_states,
                "state_ref",
                "Participant resource-budget state map key must equal state_ref",
            ),
            (
                self.participant_resource_pool_states,
                "pool_state_ref",
                "Participant resource-pool state map key must equal pool_state_ref",
            ),
            (
                self.participant_resource_budget_events,
                "event_id",
                "Participant resource-budget event map key must equal event_id",
            ),
        )
        for values, attribute, message in key_checks:
            _require_embedded_map_keys(values, attribute, message)
        for participant_address, records in self.information_state_history.items():
            if any(record.participant_address != participant_address for record in records):
                raise ValueError("Information-state history map key must equal embedded participant_address")
        _validate_execution_service_budget_projection(
            self.participant_execution_services,
            self.participant_resource_budget_states,
        )
        observation_keys = [
            (entry.address, entry.field_path, entry.domain, entry.requirement_kind)
            for entry in self.realization_observations
        ]
        if len(observation_keys) != len(set(observation_keys)):
            raise ValueError("Runtime snapshot realization_observations must identify unique concerns")
        return self

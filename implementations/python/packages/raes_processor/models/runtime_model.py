"""Top-level compiled RuntimeModel, ExecutionPlan, and resource payload projection."""

from dataclasses import asdict, dataclass, field
from typing import Any

from raes.scenario import InstantiatedScenario
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.addressing import require_compiled_address
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.evaluation import EvaluationExecutionContract, EvaluationResultContract
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
from raes_contracts.runtime_state import RuntimeSnapshot

from raes_processor.semantics.realization import CompiledRealizationAuthority, CompiledRealizationRequirement

from ..capture_admission import CaptureDemand
from .behavior_resources import (
    EventRuntime,
    ObjectiveWindowReferenceRuntime,
    ParticipantBehaviorRuntime,
    ParticipantBehaviorSpecificationRuntime,
    ParticipantInjectDeliveryRuntime,
    ParticipantObservationBoundaryRuntime,
    ParticipantOutcomeInterpretationRuleRuntime,
    ParticipantToolAffordanceRuntime,
    ScriptRuntime,
    StoryRuntime,
    WorkflowRuntime,
)
from .resources import (
    AccountPlacement,
    AssertionRuntime,
    ConditionBinding,
    ContentPlacement,
    DomainControllerPlacement,
    FeatureBinding,
    GeneratedArtifactRuntime,
    InjectBinding,
    InjectRuntime,
    NetworkRuntime,
    NodeRuntime,
    ParticipantActionContractRuntime,
    PersistentVolumeRuntime,
    PropositionRuntime,
    ResolvedResource,
    RuntimeTemplate,
)
from .time_model import CompiledTimeModel


@dataclass(frozen=True)
class ObjectiveRuntime(ResolvedResource):
    """Resolved objective node."""

    actor_type: str = ""
    actor_name: str = ""
    success_addresses: tuple[str, ...] = ()
    objective_dependencies: tuple[str, ...] = ()
    window_story_addresses: tuple[str, ...] = ()
    window_script_addresses: tuple[str, ...] = ()
    window_event_addresses: tuple[str, ...] = ()
    window_workflow_addresses: tuple[str, ...] = ()
    window_step_refs: tuple[str, ...] = ()
    window_step_workflow_addresses: tuple[str, ...] = ()
    window_references: tuple[ObjectiveWindowReferenceRuntime, ...] = ()
    result_contract: "EvaluationResultContract" = field(
        default_factory=lambda: EvaluationResultContract(resource_type="objective")
    )
    execution_contract: "EvaluationExecutionContract" = field(
        default_factory=lambda: EvaluationExecutionContract(resource_type="objective")
    )


@dataclass(frozen=True)
class CompiledCapabilityConstraint:
    """One finite SDL capability domain lowered onto a compiled resource."""

    address: str
    concern: str
    parameter: tuple[str, ...]
    allowed_values: tuple[str | int | float | bool, ...]

    def __post_init__(self) -> None:
        require_compiled_address(self.address, field_name="capability constraint address")
        if self.concern not in {
            "nodes.os",
            "nodes.os_distribution",
            "nodes.os_version",
            "nodes.architecture",
            "infrastructure.count",
        }:
            raise ValueError("compiled capability constraint has an unsupported concern")
        if not self.parameter or any(not segment for segment in self.parameter):
            raise ValueError("compiled capability constraint requires a parameter identity")
        if not self.allowed_values:
            raise ValueError("compiled capability constraint requires a non-empty domain")


@dataclass(frozen=True)
class RuntimeModel:
    """Compiled SDL runtime model.

    Reusable definitions stay as templates or metadata. Only bound runtime
    instances become planned resources.
    """

    scenario_name: str
    feature_templates: dict[str, RuntimeTemplate] = field(default_factory=dict)
    condition_templates: dict[str, RuntimeTemplate] = field(default_factory=dict)
    inject_templates: dict[str, RuntimeTemplate] = field(default_factory=dict)
    vulnerability_templates: dict[str, RuntimeTemplate] = field(default_factory=dict)
    entity_specs: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_specs: dict[str, dict[str, Any]] = field(default_factory=dict)
    relationship_specs: dict[str, dict[str, Any]] = field(default_factory=dict)
    time_model: CompiledTimeModel = field(default_factory=CompiledTimeModel)
    # Typed compiler metadata for finite pre-instantiation domains. It is
    # consumed by planner capability checks and never enters backend resource
    # payloads.
    capability_constraints: tuple[CompiledCapabilityConstraint, ...] = ()
    capture_demands: tuple[CaptureDemand, ...] = ()
    networks: dict[str, NetworkRuntime] = field(default_factory=dict)
    node_deployments: dict[str, NodeRuntime] = field(default_factory=dict)
    feature_bindings: dict[str, FeatureBinding] = field(default_factory=dict)
    propositions: dict[str, PropositionRuntime] = field(default_factory=dict)
    assertions: dict[str, AssertionRuntime] = field(default_factory=dict)
    condition_bindings: dict[str, ConditionBinding] = field(default_factory=dict)
    injects: dict[str, InjectRuntime] = field(default_factory=dict)
    inject_bindings: dict[str, InjectBinding] = field(default_factory=dict)
    content_placements: dict[str, ContentPlacement] = field(default_factory=dict)
    domain_controller_placements: dict[str, DomainControllerPlacement] = field(default_factory=dict)
    account_placements: dict[str, AccountPlacement] = field(default_factory=dict)
    generated_artifacts: dict[str, GeneratedArtifactRuntime] = field(default_factory=dict)
    persistent_volumes: dict[str, PersistentVolumeRuntime] = field(default_factory=dict)
    action_contracts: dict[str, ParticipantActionContractRuntime] = field(default_factory=dict)
    observation_boundaries: dict[str, ParticipantObservationBoundaryRuntime] = field(default_factory=dict)
    outcome_interpretation_rules: dict[str, ParticipantOutcomeInterpretationRuleRuntime] = field(default_factory=dict)
    participant_behaviors: dict[str, ParticipantBehaviorRuntime] = field(default_factory=dict)
    behavior_specifications: dict[str, ParticipantBehaviorSpecificationRuntime] = field(default_factory=dict)
    tool_affordances: dict[str, ParticipantToolAffordanceRuntime] = field(default_factory=dict)
    participant_inject_deliveries: dict[str, ParticipantInjectDeliveryRuntime] = field(default_factory=dict)
    events: dict[str, EventRuntime] = field(default_factory=dict)
    scripts: dict[str, ScriptRuntime] = field(default_factory=dict)
    stories: dict[str, StoryRuntime] = field(default_factory=dict)
    workflows: dict[str, WorkflowRuntime] = field(default_factory=dict)
    objectives: dict[str, ObjectiveRuntime] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    # SEM-218 typed compiler emission: each authored realization concern with
    # its preserved explicitness class. Model-side metadata; it never enters the backend-facing
    # `resource_payload()` envelope. Consumed by the planner realization gate.
    realization_requirements: tuple[CompiledRealizationRequirement, ...] = ()
    # Complete SEM-218 posture projection, including closed omissions and the
    # source of unresolved apparatus delegation. Planning resolves it into the
    # portable ProvisioningPlan authority collection.
    realization_authority: tuple[CompiledRealizationAuthority, ...] = ()
    realization_instance: InstantiatedScenario | None = None

    def __post_init__(self) -> None:
        owners: dict[str, str] = {}
        address_map_fields = (
            "networks",
            "node_deployments",
            "feature_bindings",
            "propositions",
            "assertions",
            "condition_bindings",
            "injects",
            "inject_bindings",
            "content_placements",
            "domain_controller_placements",
            "account_placements",
            "generated_artifacts",
            "persistent_volumes",
            "action_contracts",
            "observation_boundaries",
            "outcome_interpretation_rules",
            "participant_behaviors",
            "behavior_specifications",
            "tool_affordances",
            "participant_inject_deliveries",
            "events",
            "scripts",
            "stories",
            "workflows",
            "objectives",
        )
        for field_name in address_map_fields:
            value = getattr(self, field_name)
            for map_key, item in value.items():
                address = getattr(item, "address", None)
                if not isinstance(address, str):
                    raise TypeError(f"RuntimeModel {field_name} entries must carry an address")
                require_compiled_address(address)
                require_compiled_address(map_key, field_name="runtime model map key")
                if map_key != address:
                    raise ValueError(f"RuntimeModel {field_name} map key must equal embedded address")
                previous_owner = owners.get(address)
                if previous_owner is not None and previous_owner != field_name:
                    raise ValueError(
                        f"RuntimeModel duplicate compiled address across {previous_owner} and {field_name}"
                    )
                owners[address] = field_name
        capability_keys = [(constraint.address, constraint.concern) for constraint in self.capability_constraints]
        if len(capability_keys) != len(set(capability_keys)):
            raise ValueError("RuntimeModel capability constraints must address unique fields")


@dataclass(frozen=True)
class ExecutionPlan:
    """Composite runtime execution plan."""

    target_name: str | None
    manifest: BackendManifest
    base_snapshot: "RuntimeSnapshot"
    scenario_name: str
    model: RuntimeModel
    provisioning: ProvisioningPlan
    orchestration: OrchestrationPlan
    evaluation: EvaluationPlan
    diagnostics: list[Diagnostic] = field(default_factory=list)
    artifact_availability: ArtifactAvailabilityContext = field(
        default_factory=ArtifactAvailabilityContext,
    )

    @property
    def is_valid(self) -> bool:
        return not any(diag.is_error for diag in self.diagnostics)


def resource_payload(resource: ResolvedResource) -> dict[str, Any]:
    """Convert a compiled resource to a stable planner payload."""

    payload = asdict(resource)
    payload.pop("address", None)
    payload.pop("ordering_dependencies", None)
    payload.pop("refresh_dependencies", None)
    return payload

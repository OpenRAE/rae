"""Runtime data models for the SDL-native execution layer.

The runtime is split into three domains:

- provisioning: desired deployed state
- orchestration: resolved exercise control graph
- evaluation: resolved monitoring/scoring graph

The compiler produces a ``RuntimeModel`` with reusable templates separated
from bound runtime instances. The planner reconciles those instances against
the current ``RuntimeSnapshot`` and emits a composite ``ExecutionPlan``.
"""

from raes.participant_temporal_semantics import ParticipantTemporalState as ParticipantTemporalState
from raes_contracts.diagnostics import Diagnostic as Diagnostic
from raes_contracts.diagnostics import Severity as Severity
from raes_contracts.evaluation import EvaluationExecutionContract as EvaluationExecutionContract
from raes_contracts.evaluation import EvaluationExecutionState as EvaluationExecutionState
from raes_contracts.evaluation import EvaluationHistoryEvent as EvaluationHistoryEvent
from raes_contracts.evaluation import EvaluationHistoryEventType as EvaluationHistoryEventType
from raes_contracts.evaluation import EvaluationResultContract as EvaluationResultContract
from raes_contracts.evaluation import EvaluationResultStatus as EvaluationResultStatus
from raes_contracts.evaluation import validate_evaluation_result as validate_evaluation_result
from raes_contracts.participant_behavior import (
    ParticipantActionPreconditionStatus as ParticipantActionPreconditionStatus,
)
from raes_contracts.participant_behavior import ParticipantActionResultStatus as ParticipantActionResultStatus
from raes_contracts.participant_behavior import ParticipantAdmissionDisposition as ParticipantAdmissionDisposition
from raes_contracts.participant_behavior import (
    ParticipantBehaviorHistoryEventType as ParticipantBehaviorHistoryEventType,
)
from raes_contracts.participant_behavior import ParticipantLifecycleOperationState as ParticipantLifecycleOperationState
from raes_contracts.participant_behavior import ParticipantObservationStatus as ParticipantObservationStatus
from raes_contracts.participant_behavior import ParticipantPhaseRealization as ParticipantPhaseRealization
from raes_contracts.participant_behavior import ParticipantRuntimeLifecyclePhase as ParticipantRuntimeLifecyclePhase
from raes_contracts.participant_behavior import (
    participant_lifecycle_field_violation_messages as participant_lifecycle_field_violation_messages,
)
from raes_contracts.participant_episode import ParticipantEpisodeControlAction as ParticipantEpisodeControlAction
from raes_contracts.participant_episode import ParticipantEpisodeExecutionState as ParticipantEpisodeExecutionState
from raes_contracts.participant_episode import ParticipantEpisodeHistoryEvent as ParticipantEpisodeHistoryEvent
from raes_contracts.participant_episode import ParticipantEpisodeHistoryEventType as ParticipantEpisodeHistoryEventType
from raes_contracts.participant_episode import (
    ParticipantEpisodeInitializeRequest as ParticipantEpisodeInitializeRequest,
)
from raes_contracts.participant_episode import ParticipantEpisodeResetRequest as ParticipantEpisodeResetRequest
from raes_contracts.participant_episode import ParticipantEpisodeRestartRequest as ParticipantEpisodeRestartRequest
from raes_contracts.participant_episode import ParticipantEpisodeStatus as ParticipantEpisodeStatus
from raes_contracts.participant_episode import ParticipantEpisodeTerminalReason as ParticipantEpisodeTerminalReason
from raes_contracts.participant_episode import ParticipantEpisodeTerminateRequest as ParticipantEpisodeTerminateRequest
from raes_contracts.participant_episode import (
    iter_participant_episode_snapshot_violations as iter_participant_episode_snapshot_violations,
)
from raes_contracts.planning import ChangeAction as ChangeAction
from raes_contracts.planning import EvaluationOp as EvaluationOp
from raes_contracts.planning import EvaluationPlan as EvaluationPlan
from raes_contracts.planning import OrchestrationOp as OrchestrationOp
from raes_contracts.planning import OrchestrationPlan as OrchestrationPlan
from raes_contracts.planning import PlannedRealizationConstraint as PlannedRealizationConstraint
from raes_contracts.planning import PlannedResource as PlannedResource
from raes_contracts.planning import PlanOperation as PlanOperation
from raes_contracts.planning import ProvisioningPlan as ProvisioningPlan
from raes_contracts.planning import ProvisionOp as ProvisionOp
from raes_contracts.planning import RuntimeDomain as RuntimeDomain
from raes_contracts.runtime_state import ApplyResult as ApplyResult
from raes_contracts.runtime_state import OperationAdmissionContext as OperationAdmissionContext
from raes_contracts.runtime_state import OperationKind as OperationKind
from raes_contracts.runtime_state import OperationReceipt as OperationReceipt
from raes_contracts.runtime_state import OperationState as OperationState
from raes_contracts.runtime_state import OperationStatus as OperationStatus
from raes_contracts.runtime_state import RealizationProvenanceEntry as RealizationProvenanceEntry
from raes_contracts.runtime_state import RuntimeSnapshot as RuntimeSnapshot
from raes_contracts.runtime_state import RuntimeSnapshotEnvelope as RuntimeSnapshotEnvelope
from raes_contracts.runtime_state import SnapshotEntry as SnapshotEntry
from raes_contracts.versions import EVALUATION_STATE_SCHEMA_VERSION as EVALUATION_STATE_SCHEMA_VERSION
from raes_contracts.versions import OPERATION_SCHEMA_VERSION as OPERATION_SCHEMA_VERSION
from raes_contracts.versions import PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION as PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION
from raes_contracts.versions import RUNTIME_SNAPSHOT_SCHEMA_VERSION as RUNTIME_SNAPSHOT_SCHEMA_VERSION
from raes_contracts.versions import WORKFLOW_STATE_SCHEMA_VERSION as WORKFLOW_STATE_SCHEMA_VERSION
from raes_contracts.workflow import WorkflowCancellationRequest as WorkflowCancellationRequest
from raes_contracts.workflow import WorkflowCompensationStatus as WorkflowCompensationStatus
from raes_contracts.workflow import WorkflowExecutionContract as WorkflowExecutionContract
from raes_contracts.workflow import WorkflowExecutionState as WorkflowExecutionState
from raes_contracts.workflow import WorkflowHistoryEvent as WorkflowHistoryEvent
from raes_contracts.workflow import WorkflowHistoryEventType as WorkflowHistoryEventType
from raes_contracts.workflow import WorkflowResultContract as WorkflowResultContract
from raes_contracts.workflow import WorkflowStatus as WorkflowStatus
from raes_contracts.workflow import WorkflowStepExecutionState as WorkflowStepExecutionState
from raes_contracts.workflow import WorkflowStepLifecycle as WorkflowStepLifecycle
from raes_contracts.workflow import WorkflowStepOutcome as WorkflowStepOutcome
from raes_contracts.workflow import validate_workflow_step_result_contract as validate_workflow_step_result_contract

from raes_processor.semantics.realization import CompiledRealizationRequirement as CompiledRealizationRequirement

from .action_results import (
    ParticipantActionEffectResult,
    ParticipantActionPreconditionResult,
    ParticipantActionResult,
)
from .attribution import (
    ParticipantAttributionCandidate,
    ParticipantAttributionEdge,
    ParticipantAttributionEvidenceBasis,
    ParticipantAttributionOrderingBasis,
)
from .behavior_history_violations import (
    ParticipantHistoryAddressScope,
    iter_participant_behavior_history_violations,
    iter_participant_behavior_joint_action_violations,
)
from .behavior_resources import (
    EventRuntime,
    MixedControlControllerStateRuntime,
    MixedControlDispositionRulesRuntime,
    MixedControlTransitionRuntime,
    ObjectiveWindowReferenceRuntime,
    ParticipantAutonomousExecutionRuntime,
    ParticipantBehaviorRuntime,
    ParticipantBehaviorSpecificationRuntime,
    ParticipantExecutionBindingRuntime,
    ParticipantInjectDeliveryRuntime,
    ParticipantInteractiveAccessRuntime,
    ParticipantObservationBoundaryRuntime,
    ParticipantOutcomeInterpretationRuleRuntime,
    ParticipantResourceDemandRuntime,
    ParticipantResourceFairnessRuntime,
    ParticipantResourceOwnerRuntime,
    ParticipantToolAffordanceRuntime,
    ScriptRuntime,
    StoryRuntime,
    WorkflowPredicateRuntime,
    WorkflowRuntime,
    WorkflowStepRuntime,
    WorkflowStepStatePredicateRuntime,
    WorkflowSwitchCaseRuntime,
)
from .decision_surface import (
    ParticipantDecisionSurfaceActionAssessment,
    ParticipantDecisionSurfaceProjectionInput,
    project_participant_decision_surface,
)
from .decision_surface_anchor_v2 import (
    ParticipantBehaviorProjectionAnchorRequestV2,
    resolve_participant_behavior_projection_anchor_v2,
    resolve_participant_episode_readiness_anchor_v2,
    validate_participant_decision_surface_v2_anchor,
)
from .decision_surface_v2 import (
    ParticipantDecisionSurfaceProjectionInputV2,
    project_participant_decision_surface_v2,
)
from .history_event import (
    ParticipantBehaviorHistoryEvent,
)
from .outcome import (
    ParticipantOutcomeInterpretationRecord,
    ParticipantOutcomeSourceRecord,
    ParticipantOutcomeTargetRecord,
)
from .outcome_interpretation_validation import validate_participant_outcome_interpretation_record
from .participant_action_arguments import resolve_participant_action_arguments
from .participant_exposure_authority import (
    ParticipantExposureAssessment,
    ParticipantExposureAuthorizationRecord,
    ParticipantExposureOccurrenceRecord,
    ParticipantExposurePolicyRevision,
    ParticipantExposureRealizationAssessment,
    ParticipantExposureResolvers,
)
from .participant_exposure_authority_v2 import (
    ParticipantExposureAuthorizationRecordV2,
    ParticipantExposurePolicyDecisionV2,
    ParticipantExposureResolversV2,
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
    ServiceContentMaterializationBinding,
    ServiceSearchIndexSchemaMaterializationBinding,
    map_backend_diagnostic_to_participant_failure,
    validate_participant_action_result_contract,
)
from .runtime_model import (
    CompiledCapabilityConstraint,
    ExecutionPlan,
    ObjectiveRuntime,
    RuntimeModel,
    resource_payload,
)
from .temporal import (
    ParticipantTemporalRuntimeContext,
    ParticipantTemporalStateTransition,
    iter_participant_temporal_state_machine_violations,
)
from .time_model import (
    CompiledClock,
    CompiledTemporalConstraint,
    CompiledTimeDomain,
    CompiledTimeDomainMapping,
    CompiledTimeModel,
    CompiledTimeProgressionPolicy,
)

__all__ = [
    "AccountPlacement",
    "ApplyResult",
    "AssertionRuntime",
    "ChangeAction",
    "CompiledCapabilityConstraint",
    "CompiledClock",
    "CompiledRealizationRequirement",
    "CompiledTemporalConstraint",
    "CompiledTimeDomain",
    "CompiledTimeDomainMapping",
    "CompiledTimeModel",
    "CompiledTimeProgressionPolicy",
    "ConditionBinding",
    "ContentPlacement",
    "ServiceContentMaterializationBinding",
    "ServiceSearchIndexSchemaMaterializationBinding",
    "DomainControllerPlacement",
    "GeneratedArtifactRuntime",
    "Diagnostic",
    "EVALUATION_STATE_SCHEMA_VERSION",
    "EvaluationExecutionContract",
    "EvaluationExecutionState",
    "EvaluationHistoryEvent",
    "EvaluationHistoryEventType",
    "EvaluationOp",
    "EvaluationPlan",
    "EvaluationResultContract",
    "EvaluationResultStatus",
    "EventRuntime",
    "ExecutionPlan",
    "FeatureBinding",
    "InjectBinding",
    "InjectRuntime",
    "NetworkRuntime",
    "NodeRuntime",
    "OPERATION_SCHEMA_VERSION",
    "ObjectiveRuntime",
    "ObjectiveWindowReferenceRuntime",
    "MixedControlControllerStateRuntime",
    "MixedControlDispositionRulesRuntime",
    "MixedControlTransitionRuntime",
    "OperationReceipt",
    "OperationAdmissionContext",
    "OperationKind",
    "OperationState",
    "OperationStatus",
    "OrchestrationOp",
    "OrchestrationPlan",
    "PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION",
    "ParticipantActionContractRuntime",
    "PersistentVolumeRuntime",
    "ParticipantActionEffectResult",
    "ParticipantActionPreconditionResult",
    "ParticipantActionPreconditionStatus",
    "ParticipantActionResult",
    "ParticipantActionResultStatus",
    "ParticipantAdmissionDisposition",
    "ParticipantAttributionCandidate",
    "ParticipantAttributionEdge",
    "ParticipantAttributionEvidenceBasis",
    "ParticipantAttributionOrderingBasis",
    "ParticipantBehaviorHistoryEvent",
    "ParticipantBehaviorHistoryEventType",
    "ParticipantDecisionSurfaceActionAssessment",
    "ParticipantDecisionSurfaceProjectionInput",
    "ParticipantExposureAssessment",
    "ParticipantExposureAuthorizationRecord",
    "ParticipantExposureOccurrenceRecord",
    "ParticipantExposurePolicyRevision",
    "ParticipantExposureRealizationAssessment",
    "ParticipantExposureResolvers",
    "ParticipantBehaviorRuntime",
    "ParticipantBehaviorProjectionAnchorRequestV2",
    "ParticipantBehaviorSpecificationRuntime",
    "ParticipantInjectDeliveryRuntime",
    "ParticipantAutonomousExecutionRuntime",
    "ParticipantExecutionBindingRuntime",
    "ParticipantResourceDemandRuntime",
    "ParticipantResourceFairnessRuntime",
    "ParticipantResourceOwnerRuntime",
    "ParticipantInteractiveAccessRuntime",
    "ParticipantEpisodeControlAction",
    "ParticipantEpisodeExecutionState",
    "ParticipantEpisodeHistoryEvent",
    "ParticipantEpisodeHistoryEventType",
    "ParticipantEpisodeInitializeRequest",
    "ParticipantEpisodeResetRequest",
    "ParticipantEpisodeRestartRequest",
    "ParticipantEpisodeStatus",
    "ParticipantEpisodeTerminalReason",
    "ParticipantEpisodeTerminateRequest",
    "ParticipantHistoryAddressScope",
    "ParticipantLifecycleOperationState",
    "ParticipantObservationBoundaryRuntime",
    "ParticipantToolAffordanceRuntime",
    "ParticipantObservationStatus",
    "ParticipantOutcomeInterpretationRecord",
    "ParticipantOutcomeInterpretationRuleRuntime",
    "ParticipantOutcomeSourceRecord",
    "ParticipantOutcomeTargetRecord",
    "ParticipantPhaseRealization",
    "ParticipantRuntimeLifecyclePhase",
    "project_participant_decision_surface",
    "project_participant_decision_surface_v2",
    "resolve_participant_behavior_projection_anchor_v2",
    "resolve_participant_episode_readiness_anchor_v2",
    "ParticipantDecisionSurfaceProjectionInputV2",
    "ParticipantExposureAuthorizationRecordV2",
    "ParticipantExposurePolicyDecisionV2",
    "ParticipantExposureResolversV2",
    "ParticipantTemporalRuntimeContext",
    "ParticipantTemporalState",
    "ParticipantTemporalStateTransition",
    "PlanOperation",
    "PlannedResource",
    "PropositionRuntime",
    "ProvisionOp",
    "ProvisioningPlan",
    "RUNTIME_SNAPSHOT_SCHEMA_VERSION",
    "RealizationProvenanceEntry",
    "ResolvedResource",
    "RuntimeDomain",
    "RuntimeModel",
    "RuntimeSnapshot",
    "RuntimeSnapshotEnvelope",
    "validate_participant_decision_surface_v2_anchor",
    "RuntimeTemplate",
    "ScriptRuntime",
    "Severity",
    "SnapshotEntry",
    "StoryRuntime",
    "WORKFLOW_STATE_SCHEMA_VERSION",
    "WorkflowCancellationRequest",
    "WorkflowCompensationStatus",
    "WorkflowExecutionContract",
    "WorkflowExecutionState",
    "WorkflowHistoryEvent",
    "WorkflowHistoryEventType",
    "WorkflowPredicateRuntime",
    "WorkflowResultContract",
    "WorkflowRuntime",
    "WorkflowStatus",
    "WorkflowStepExecutionState",
    "WorkflowStepLifecycle",
    "WorkflowStepOutcome",
    "WorkflowStepRuntime",
    "WorkflowStepStatePredicateRuntime",
    "WorkflowSwitchCaseRuntime",
    "iter_participant_behavior_history_violations",
    "iter_participant_behavior_joint_action_violations",
    "iter_participant_episode_snapshot_violations",
    "iter_participant_temporal_state_machine_violations",
    "map_backend_diagnostic_to_participant_failure",
    "participant_lifecycle_field_violation_messages",
    "resource_payload",
    "resolve_participant_action_arguments",
    "validate_evaluation_result",
    "validate_participant_action_result_contract",
    "validate_participant_outcome_interpretation_record",
    "validate_workflow_step_result_contract",
]

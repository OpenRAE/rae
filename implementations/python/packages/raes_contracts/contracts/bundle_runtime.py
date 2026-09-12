"""Runtime-facing slice of the published JSON Schema bundle (split from bundle.py)."""

from __future__ import annotations

from typing import Any

from .associated_artifacts import AssociatedArtifactManifestModel
from .execution_state import EvaluationHistoryEventModel
from .experiment_bindings import ParticipantConfigurationResultModel
from .operation_carriers import OperationReceiptModel, OperationStatusModel
from .participant_context import ParticipantContextViewModel
from .participant_control import ParticipantControlOccurrenceModel
from .participant_crossing import ParticipantCrossingOccurrenceModel
from .participant_decision_surface import ParticipantDecisionSurfaceModel
from .participant_decision_surface_v2 import ParticipantDecisionSurfaceV2Model
from .participant_envelopes import (
    ParticipantJointActionRecordModel,
    ParticipantLifecycleEventModel,
    ParticipantSharedStateRecordModel,
    ParticipantTimeManagementContextModel,
)
from .participant_execution import (
    ParticipantExecutionBindingModel,
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from .participant_flow_control import ParticipantFlowControlRelationModel
from .participant_information_state import ParticipantInformationStateRecordModel
from .participant_observation import ParticipantObservationEnvelopeModel
from .participant_resource_budgets import (
    ParticipantResourceBudgetEventModel,
    ParticipantResourceBudgetPolicyModel,
    ParticipantResourceBudgetStateModel,
    ParticipantResourcePoolCapacityModel,
)
from .participant_runtime import (
    ParticipantBehaviorHistoryEventModel,
    ParticipantEpisodeHistoryEventModel,
    ParticipantEpisodeStateModel,
)
from .participant_views import (
    ParticipantHistoryViewModel,
    ParticipantOutcomeReportModel,
    ParticipantStatusViewModel,
)
from .reusable_assets import (
    ReusableAssetTrustPolicyModel,
    _event_stream_schema,
)
from .runtime_facts import RuntimeFactBindingPlaneModel


def _runtime_schema_bundle() -> dict[str, dict[str, Any]]:
    return {
        "evaluation-history-event-stream-v1": _event_stream_schema(
            "EvaluationHistoryEventStream",
            EvaluationHistoryEventModel.model_json_schema(),
        ),
        "participant-episode-state-envelope-v1": ParticipantEpisodeStateModel.model_json_schema(),
        "participant-episode-history-event-stream-v1": _event_stream_schema(
            "ParticipantEpisodeHistoryEventStream",
            ParticipantEpisodeHistoryEventModel.model_json_schema(),
        ),
        "participant-behavior-history-event-stream-v1": _event_stream_schema(
            "ParticipantBehaviorHistoryEventStream",
            ParticipantBehaviorHistoryEventModel.model_json_schema(),
        ),
        "participant-execution-binding-v1": ParticipantExecutionBindingModel.model_json_schema(),
        "participant-execution-control-v1": ParticipantExecutionControlRequestModel.model_json_schema(),
        "participant-execution-service-state-v1": ParticipantExecutionServiceStateModel.model_json_schema(),
        "participant-resource-budget-policy-v1": ParticipantResourceBudgetPolicyModel.model_json_schema(),
        "participant-resource-pool-capacity-v1": ParticipantResourcePoolCapacityModel.model_json_schema(),
        "participant-resource-budget-state-v1": ParticipantResourceBudgetStateModel.model_json_schema(),
        "participant-resource-budget-event-v1": ParticipantResourceBudgetEventModel.model_json_schema(),
        "participant-lifecycle-event-v1": ParticipantLifecycleEventModel.model_json_schema(),
        "participant-observation-envelope-v1": ParticipantObservationEnvelopeModel.model_json_schema(),
        "participant-information-state-record-v1": ParticipantInformationStateRecordModel.model_json_schema(),
        "participant-shared-state-record-v1": ParticipantSharedStateRecordModel.model_json_schema(),
        "participant-joint-action-record-v1": ParticipantJointActionRecordModel.model_json_schema(),
        "participant-time-management-context-v1": ParticipantTimeManagementContextModel.model_json_schema(),
        "participant-control-occurrence-v1": ParticipantControlOccurrenceModel.model_json_schema(),
        "participant-crossing-occurrence-v1": ParticipantCrossingOccurrenceModel.model_json_schema(),
        "participant-flow-control-relation-v1": ParticipantFlowControlRelationModel.model_json_schema(),
        "participant-outcome-report-v1": ParticipantOutcomeReportModel.model_json_schema(),
        "participant-status-view-v1": ParticipantStatusViewModel.model_json_schema(),
        "participant-history-view-v1": ParticipantHistoryViewModel.model_json_schema(),
        "participant-context-view-v1": ParticipantContextViewModel.model_json_schema(),
        "runtime-fact-binding-plane-v1": RuntimeFactBindingPlaneModel.model_json_schema(),
        "participant-decision-surface-v1": ParticipantDecisionSurfaceModel.model_json_schema(),
        "participant-decision-surface-v2": ParticipantDecisionSurfaceV2Model.model_json_schema(),
        "participant-configuration-result-v1": ParticipantConfigurationResultModel.model_json_schema(),
        "operation-receipt-v1": OperationReceiptModel.model_json_schema(),
        "operation-status-v1": OperationStatusModel.model_json_schema(),
        "associated-artifact-manifest-v1": AssociatedArtifactManifestModel.model_json_schema(),
        "reusable-asset-trust-policy-v1": ReusableAssetTrustPolicyModel.model_json_schema(),
    }

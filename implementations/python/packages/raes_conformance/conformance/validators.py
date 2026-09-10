"""Contract validator registries and structural payload validation."""

from __future__ import annotations

from raes_contracts.behavioral_relation_profiles import BehavioralRelationProfileModel
from raes_contracts.behavioral_relations import BehavioralRelationCatalogModel
from raes_contracts.contracts import (
    ActivityStreamsActivityTypesSourceModel,
    ArtifactTransformationReportModel,
    AssociatedArtifactManifestModel,
    BackendManifestV2Model,
    CandidateSynthesisInputModel,
    CandidateSynthesisProfileDefinitionModel,
    CandidateSynthesisRecordModel,
    EvaluationHistoryEventModel,
    EvaluationPlanModel,
    EvaluationResultStateModel,
    ExperimentApparatusContextModel,
    ExperimentBindingDescriptorSetModel,
    ExperimentCaptureSpecModel,
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ExperimentStudyModel,
    ExternalConceptBindingDocumentModel,
    FipaCommunicativeActsSourceModel,
    OperationReceiptModel,
    OperationStatusModel,
    OrchestrationPlanModel,
    ParticipantBehaviorHistoryEventModel,
    ParticipantBoundaryFlowPolicyProfileModel,
    ParticipantConfigurationResultModel,
    ParticipantControlOccurrenceModel,
    ParticipantCrossingOccurrenceModel,
    ParticipantEpisodeHistoryEventModel,
    ParticipantEpisodeStateModel,
    ParticipantFlowControlContextResolver,
    ParticipantFlowControlRelationModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationProvenanceModel,
    ParticipantInformationReconstructionProfileModel,
    ParticipantInformationStateContextResolver,
    ParticipantInformationStateRecordModel,
    ParticipantLifecycleEventModel,
    ParticipantObservationEnvelopeModel,
    ParticipantSharedStateRecordModel,
    ProvisioningPlanModel,
    RuntimeFactBindingPlaneModel,
    RuntimeSnapshotEnvelopeModel,
    SemanticProjectionReportModel,
    ValidationBasisDisclosureDocumentModel,
    WorkflowExecutionStateModel,
    WorkflowHistoryEventModel,
    validate_participant_flow_control_resolved_context,
    validate_participant_information_state_resolved_context,
)
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionBindingModel,
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import (
    DomainProfileAdmissionPolicyModel,
    DomainProfileBindingModel,
    DomainProfileDefinitionModel,
    DomainProfileResolutionContextModel,
    DomainProfileSupportDeclarationModel,
)
from raes_contracts.observation_demand import ObservationDemandDocument
from raes_contracts.participant_opacity import (
    ParticipantOpacityAnalysisEvidenceModel,
    ParticipantOpacityAnalysisInputModel,
    ParticipantOpacityModelCheckEvidenceModel,
    ParticipantOpacityModelCheckInputModel,
)
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_contracts.scientific_completeness import (
    ScientificCompletenessAssessmentModel,
    ScientificCompletenessTaxonomyModel,
)
from raes_contracts.validation_profiles import ValidationProfileCatalogModel

from raes_conformance.conformance.diagnostics import _diagnostic, sanitized_failure_message

_SCHEMA_INVALID_DIAGNOSTIC_CODE = "conformance.schema-invalid"
_MODEL_VALIDATORS = {
    "backend-manifest-v2": BackendManifestV2Model.model_validate,
    "participant-implementation-manifest-v1": ParticipantImplementationManifestModel.model_validate,
    "participant-implementation-provenance-v1": ParticipantImplementationProvenanceModel.model_validate,
    "provisioning-plan-v1": ProvisioningPlanModel.model_validate,
    "orchestration-plan-v1": OrchestrationPlanModel.model_validate,
    "evaluation-plan-v1": EvaluationPlanModel.model_validate,
    "operation-receipt-v1": OperationReceiptModel.model_validate,
    "operation-status-v1": OperationStatusModel.model_validate,
    "runtime-snapshot-v1": RuntimeSnapshotEnvelopeModel.model_validate,
    "runtime-fact-binding-plane-v1": RuntimeFactBindingPlaneModel.model_validate,
    "workflow-result-envelope-v1": WorkflowExecutionStateModel.model_validate,
    "evaluation-result-envelope-v1": EvaluationResultStateModel.model_validate,
    "participant-episode-state-envelope-v1": ParticipantEpisodeStateModel.model_validate,
    "participant-execution-binding-v1": ParticipantExecutionBindingModel.model_validate,
    "participant-execution-control-v1": ParticipantExecutionControlRequestModel.model_validate,
    "participant-execution-service-state-v1": ParticipantExecutionServiceStateModel.model_validate,
    "participant-lifecycle-event-v1": ParticipantLifecycleEventModel.model_validate,
    "participant-observation-envelope-v1": ParticipantObservationEnvelopeModel.model_validate,
    "participant-information-state-record-v1": ParticipantInformationStateRecordModel.model_validate,
    "participant-information-reconstruction-profile-v1": (
        ParticipantInformationReconstructionProfileModel.model_validate
    ),
    "participant-boundary-flow-policy-v1": ParticipantBoundaryFlowPolicyProfileModel.model_validate,
    "participant-shared-state-record-v1": ParticipantSharedStateRecordModel.model_validate,
    "participant-control-occurrence-v1": ParticipantControlOccurrenceModel.model_validate,
    "participant-crossing-occurrence-v1": ParticipantCrossingOccurrenceModel.model_validate,
    "participant-flow-control-relation-v1": ParticipantFlowControlRelationModel.model_validate,
    "experiment-capture-spec-v1": ExperimentCaptureSpecModel.model_validate,
    "experiment-evidence-record-v1": ExperimentEvidenceRecordModel.model_validate,
    "experiment-derived-measure-v1": ExperimentDerivedMeasureModel.model_validate,
    "experiment-run-v1": ExperimentRunModel.model_validate,
    "experiment-binding-descriptors-v1": ExperimentBindingDescriptorSetModel.model_validate,
    "participant-configuration-result-v1": ParticipantConfigurationResultModel.model_validate,
}


_STRUCTURAL_ONLY_VALIDATORS = {
    "associated-artifact-manifest-v1": AssociatedArtifactManifestModel.model_validate,
    "artifact-transformation-report-v1": ArtifactTransformationReportModel.model_validate,
    "sdl-candidate-synthesis-input-v1": CandidateSynthesisInputModel.model_validate,
    "sdl-candidate-synthesis-profile-v1": CandidateSynthesisProfileDefinitionModel.model_validate,
    "sdl-candidate-synthesis-record-v1": CandidateSynthesisRecordModel.model_validate,
    "behavioral-relation-profile-v1": BehavioralRelationProfileModel.model_validate,
    "behavioral-relations-v1": BehavioralRelationCatalogModel.model_validate,
    "domain-profile-admission-policy-v1": DomainProfileAdmissionPolicyModel.model_validate,
    "domain-profile-binding-v1": DomainProfileBindingModel.model_validate,
    "domain-profile-definition-v1": DomainProfileDefinitionModel.model_validate,
    "domain-profile-resolution-context-v1": DomainProfileResolutionContextModel.model_validate,
    "domain-profile-support-declaration-v1": DomainProfileSupportDeclarationModel.model_validate,
    "external-concept-bindings-v1": ExternalConceptBindingDocumentModel.model_validate,
    "semantic-projection-report-v1": SemanticProjectionReportModel.model_validate,
    "fipa-communicative-acts-source-v1": FipaCommunicativeActsSourceModel.model_validate,
    "experiment-apparatus-context-v1": ExperimentApparatusContextModel.model_validate,
    "experiment-authoring-input-v1": ExperimentSpecModel.model_validate,
    "experiment-study-v1": ExperimentStudyModel.model_validate,
    "realization-envelope-v1": BackendRealizationEnvelopeModel.model_validate,
    "scientific-completeness-assessment-v1": ScientificCompletenessAssessmentModel.model_validate,
    "scientific-completeness-taxonomy-v1": ScientificCompletenessTaxonomyModel.model_validate,
    "validation-profile-catalog-v1": ValidationProfileCatalogModel.model_validate,
    "validation-basis-disclosure-v1": ValidationBasisDisclosureDocumentModel.model_validate,
    "participant-opacity-analysis-input-v1": ParticipantOpacityAnalysisInputModel.model_validate,
    "participant-opacity-analysis-evidence-v1": ParticipantOpacityAnalysisEvidenceModel.model_validate,
    "participant-opacity-model-check-input-v1": ParticipantOpacityModelCheckInputModel.model_validate,
    "participant-opacity-model-check-evidence-v1": ParticipantOpacityModelCheckEvidenceModel.model_validate,
    "w3c-activitystreams-activity-types-source-v1": ActivityStreamsActivityTypesSourceModel.model_validate,
    "observation-demand-v1": ObservationDemandDocument.model_validate,
}


_SEMANTIC_CONTEXT_REQUIRED_CONTRACTS = frozenset(
    {
        "associated-artifact-manifest-v1",
        "external-concept-bindings-v1",
        "semantic-projection-report-v1",
        "participant-information-state-record-v1",
        "participant-flow-control-relation-v1",
    }
)


_EVENT_STREAM_VALIDATORS: dict[str, tuple[type, str]] = {
    "workflow-history-event-stream-v1": (WorkflowHistoryEventModel, "workflow"),
    "evaluation-history-event-stream-v1": (EvaluationHistoryEventModel, "evaluation"),
    "participant-episode-history-event-stream-v1": (
        ParticipantEpisodeHistoryEventModel,
        "participant episode",
    ),
    "participant-behavior-history-event-stream-v1": (
        ParticipantBehaviorHistoryEventModel,
        "participant behavior",
    ),
}


def _validate_event_stream(
    *,
    contract_name: str,
    payload: object,
    model_cls: type,
    event_label: str,
) -> list[Diagnostic]:
    """Validate a published history event stream against one Pydantic model.

    Shared by the workflow, evaluation, and participant-episode history
    event streams so adding a new stream type only requires extending
    ``_EVENT_STREAM_VALIDATORS``.
    """

    if not isinstance(payload, list):
        return [
            _diagnostic(
                _SCHEMA_INVALID_DIAGNOSTIC_CODE,
                contract_name,
                f"{event_label} history payload must be a list",
            )
        ]
    diagnostics: list[Diagnostic] = []
    for index, event in enumerate(payload):
        try:
            model_cls.model_validate(event)
        except Exception as exc:
            diagnostics.append(
                _diagnostic(
                    _SCHEMA_INVALID_DIAGNOSTIC_CODE,
                    f"{contract_name}[{index}]",
                    f"{event_label} history event is invalid: {sanitized_failure_message(exc)}",
                )
            )
    return diagnostics


def _validate_payload(contract_name: str, payload: object) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    validator = _MODEL_VALIDATORS.get(contract_name) or _STRUCTURAL_ONLY_VALIDATORS.get(contract_name)
    if validator is not None:
        try:
            validator(payload)
        except Exception as exc:
            diagnostics.append(
                _diagnostic(
                    _SCHEMA_INVALID_DIAGNOSTIC_CODE,
                    contract_name,
                    f"{contract_name} failed contract validation: {sanitized_failure_message(exc)}",
                )
            )
            return diagnostics
    elif contract_name in _EVENT_STREAM_VALIDATORS:
        diagnostics.extend(
            _validate_event_stream(
                contract_name=contract_name,
                payload=payload,
                model_cls=_EVENT_STREAM_VALIDATORS[contract_name][0],
                event_label=_EVENT_STREAM_VALIDATORS[contract_name][1],
            )
        )
    else:
        diagnostics.append(
            _diagnostic(
                "conformance.contract-unknown",
                contract_name,
                f"No conformance validator is registered for {contract_name}.",
            )
        )
    return diagnostics


def _information_state_context_diagnostics(
    payload: object,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> list[Diagnostic]:
    contract_name = "participant-information-state-record-v1"
    diagnostics: list[Diagnostic] = []
    if information_state_context_resolver is None:
        diagnostics.append(
            _diagnostic(
                "conformance.semantic-context-required",
                contract_name,
                "participant information-state context resolver is required",
            )
        )
    else:
        try:
            record = ParticipantInformationStateRecordModel.model_validate(payload)
            validate_participant_information_state_resolved_context(
                record,
                information_state_context_resolver,
                payload,
            )
        except (TypeError, ValueError) as exc:
            diagnostics.append(
                _diagnostic(
                    "conformance.semantic-invalid",
                    contract_name,
                    "participant information-state context is invalid: " + sanitized_failure_message(exc),
                )
            )
    return diagnostics


def _flow_control_context_diagnostics(
    payload: object,
    flow_control_context_resolver: ParticipantFlowControlContextResolver | None = None,
) -> list[Diagnostic]:
    contract_name = "participant-flow-control-relation-v1"
    if flow_control_context_resolver is None:
        return [
            _diagnostic(
                "conformance.semantic-context-required",
                contract_name,
                "participant flow-control context resolver is required",
            )
        ]
    try:
        document = ParticipantFlowControlRelationModel.model_validate(payload)
        validate_participant_flow_control_resolved_context(
            document,
            flow_control_context_resolver,
            payload,
        )
    except (TypeError, ValueError) as exc:
        return [
            _diagnostic(
                "conformance.semantic-invalid",
                contract_name,
                "participant flow-control context is invalid: " + sanitized_failure_message(exc),
            )
        ]
    return []


def validate_contract_payload(
    contract_name: str,
    payload: object,
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
    flow_control_context_resolver: ParticipantFlowControlContextResolver | None = None,
) -> tuple[Diagnostic, ...]:
    """Validate one payload through its structural and available contextual boundary."""

    diagnostics = _validate_payload(contract_name, payload)
    if not diagnostics and contract_name == "participant-information-state-record-v1":
        diagnostics.extend(_information_state_context_diagnostics(payload, information_state_context_resolver))
    if not diagnostics and contract_name == "participant-flow-control-relation-v1":
        diagnostics.extend(_flow_control_context_diagnostics(payload, flow_control_context_resolver))
    return tuple(diagnostics)


def supported_contract_ids() -> tuple[str, ...]:
    """Return the contract ids owned by the conformance validator registry."""

    return tuple(sorted((*_MODEL_VALIDATORS, *_STRUCTURAL_ONLY_VALIDATORS, *_EVENT_STREAM_VALIDATORS)))


def contract_payload_root(contract_name: str) -> str | None:
    """Return the required JSON root shape for a registered contract."""

    if contract_name in _EVENT_STREAM_VALIDATORS:
        return "array"
    if contract_name in _MODEL_VALIDATORS or contract_name in _STRUCTURAL_ONLY_VALIDATORS:
        return "object"
    return None


def contract_validation_strength(contract_name: str) -> str | None:
    """Return the strongest context-free validation claim for a contract."""

    if contract_name in _SEMANTIC_CONTEXT_REQUIRED_CONTRACTS:
        strength = "structural-context-required"
    elif contract_name in _STRUCTURAL_ONLY_VALIDATORS:
        strength = "structural"
    elif contract_name in _MODEL_VALIDATORS or contract_name in _EVENT_STREAM_VALIDATORS:
        strength = "semantic"
    else:
        strength = None
    return strength

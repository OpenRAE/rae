"""Schema parts that ``raes_contracts`` owns (ADR-121).

``raes_schemas`` composes the published schemas from the parts of each owner.
This module gives the neutral contract schemas and their invariant annotations.
"""

from __future__ import annotations

from typing import Any

from raes_contracts.augmentation_preparation import AugmentationPreparation
from raes_contracts.authoring_adapters import (
    AuthoringAdapterComparisonModel,
    AuthoringAdapterProfileModel,
    AuthoringAdapterVectorModel,
)
from raes_contracts.behavioral_relation_profiles import BehavioralRelationProfileModel
from raes_contracts.behavioral_relations import BehavioralRelationCatalogModel
from raes_contracts.contracts.participant_information_reconstruction_profiles import (
    ParticipantInformationReconstructionProfileModel,
)
from raes_contracts.controlled_vocabularies import ControlledVocabularyCatalogModel
from raes_contracts.domain_profiles import (
    DomainProfileAdmissionPolicyModel,
    DomainProfileBindingModel,
    DomainProfileDefinitionModel,
    DomainProfileResolutionContextModel,
    DomainProfileSupportDeclarationModel,
)
from raes_contracts.materialization import MaterializationSubmission
from raes_contracts.materialization_inventory import RuntimeInventoryReport
from raes_contracts.observation_demand import ObservationDemandDocument
from raes_contracts.participant_opacity import (
    ParticipantOpacityAnalysisEvidenceModel,
    ParticipantOpacityAnalysisInputModel,
    ParticipantOpacityModelCheckEvidenceModel,
    ParticipantOpacityModelCheckInputModel,
)
from raes_contracts.provenance import SDLLineageLedgerModel
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
from raes_contracts.realization_profiles import PlanProfileAuthority
from raes_contracts.realization_structure import RealizationConstraintDocument
from raes_contracts.scientific_completeness import (
    ScientificCompletenessAssessmentModel,
    ScientificCompletenessTaxonomyModel,
)
from raes_contracts.semantic_comparison import SemanticComparisonRequestModel, SemanticComparisonResultModel
from raes_contracts.validation_profiles import ValidationProfileCatalogModel

from .contracts import semantic_profiles, semantic_projection
from .contracts.admitted_trial_plan import AdmittedTrialPlanModel
from .contracts.backend_preparation import BackendPreparationResponseModel
from .contracts.batch_execution import BatchExecutionReceiptModel
from .contracts.bundle_runtime import runtime_schema_bundle
from .contracts.catalogs import (
    ConceptFamilyCatalogModel,
    ReferenceModelCatalogModel,
    UcoAlignmentCatalogModel,
)
from .contracts.execution_state import (
    EvaluationResultStateModel,
    InstantiationRequestModel,
    PropositionTruthResultModel,
    WorkflowCancellationRequestModel,
    WorkflowExecutionStateModel,
    WorkflowHistoryEventModel,
)
from .contracts.experiment_apparatus import ExperimentApparatusContextModel, ExperimentTaskModel
from .contracts.experiment_bindings import (
    ExperimentBindingDescriptorSetModel,
)
from .contracts.experiment_capture import ExperimentCaptureSpecModel
from .contracts.experiment_evidence import ExperimentDerivedMeasureModel, ExperimentEvidenceRecordModel
from .contracts.experiment_run import ExperimentRunModel
from .contracts.experiment_spec import ExperimentSpecModel, ExperimentStudyModel
from .contracts.external_concept_bindings import ExternalConceptBindingDocumentModel
from .contracts.manifests import ProcessorManifestV2Model
from .contracts.materialization_attestation import MaterializationArchiveRecord
from .contracts.mixed_composition import MixedParticipantCompositionProfileModel
from .contracts.participant_flow_control import (
    ParticipantBoundaryFlowPolicyProfileModel,
)
from .contracts.participant_manifests import (
    BackendManifestV2Model,
    ParticipantImplementationManifestModel,
    ParticipantImplementationProvenanceModel,
)
from .contracts.participant_owner_flow import ParticipantOwnerFlowPolicyProfileModel
from .contracts.random_stream import RandomStreamProfileModel, RandomStreamVectorModel
from .contracts.realization_plans import (
    EvaluationPlanModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
    RuntimeSnapshotEnvelopeModel,
)
from .contracts.reusable_assets import (
    backend_profile_schema,
    event_stream_schema,
)
from .contracts.schema_constraints import raes_semantic_invariant_profile_schema
from .contracts.schema_invariants import add_raes_invariant
from .contracts.time_model import RealizedTimeModelProvenanceModel, TimeModelDeclarationModel, TimeRuntimeStateModel
from .contracts.transformation_schemas import transformation_schema_bundle
from .contracts.trial_cleanup import SchedulerIsolationProofModel, TrialCleanupPlanModel, TrialCleanupReceiptModel
from .contracts.validation_disclosure import ValidationBasisDisclosureDocumentModel
from .contracts.vocabulary_sources import (
    ActivityStreamsActivityTypesSourceModel,
    AtlasTacticsSourceModel,
    AttackEnterpriseTacticsSourceModel,
    FipaCommunicativeActsSourceModel,
    NistCsfDefensiveCategorySourceModel,
)


def _domain_profile_schema_bundle() -> dict[str, dict[str, Any]]:

    return {
        "domain-profile-definition-v1": DomainProfileDefinitionModel.model_json_schema(),
        "domain-profile-binding-v1": DomainProfileBindingModel.model_json_schema(),
        "domain-profile-resolution-context-v1": DomainProfileResolutionContextModel.model_json_schema(),
        "domain-profile-support-declaration-v1": DomainProfileSupportDeclarationModel.model_json_schema(),
        "domain-profile-admission-policy-v1": DomainProfileAdmissionPolicyModel.model_json_schema(),
    }


def _experiment_schema_bundle() -> dict[str, dict[str, Any]]:
    """Experiment, trial, time, and runtime-plan contract schemas."""

    return {
        "experiment-apparatus-context-v1": ExperimentApparatusContextModel.model_json_schema(),
        "experiment-authoring-input-v1": ExperimentSpecModel.model_json_schema(),
        "experiment-binding-descriptors-v1": ExperimentBindingDescriptorSetModel.model_json_schema(),
        "experiment-capture-spec-v1": ExperimentCaptureSpecModel.model_json_schema(),
        "experiment-derived-measure-v1": ExperimentDerivedMeasureModel.model_json_schema(),
        "experiment-evidence-record-v1": ExperimentEvidenceRecordModel.model_json_schema(),
        "experiment-run-v1": ExperimentRunModel.model_json_schema(),
        "experiment-study-v1": ExperimentStudyModel.model_json_schema(),
        "experiment-task-v1": ExperimentTaskModel.model_json_schema(),
        "admitted-trial-plan-v1": AdmittedTrialPlanModel.model_json_schema(),
        "mixed-participant-composition-profile-v1": MixedParticipantCompositionProfileModel.model_json_schema(),
        "trial-cleanup-plan-v1": TrialCleanupPlanModel.model_json_schema(),
        "trial-cleanup-receipt-v1": TrialCleanupReceiptModel.model_json_schema(),
        "scheduler-isolation-proof-v1": SchedulerIsolationProofModel.model_json_schema(),
        "batch-execution-receipt-v1": BatchExecutionReceiptModel.model_json_schema(),
        "time-model-v1": TimeModelDeclarationModel.model_json_schema(),
        "time-runtime-state-v1": TimeRuntimeStateModel.model_json_schema(),
        "realized-time-model-v1": RealizedTimeModelProvenanceModel.model_json_schema(),
        "provisioning-plan-v1": ProvisioningPlanModel.model_json_schema(),
        "orchestration-plan-v1": OrchestrationPlanModel.model_json_schema(),
        "evaluation-plan-v1": EvaluationPlanModel.model_json_schema(),
        "runtime-snapshot-v1": RuntimeSnapshotEnvelopeModel.model_json_schema(),
        "workflow-result-envelope-v1": WorkflowExecutionStateModel.model_json_schema(),
        "workflow-history-event-stream-v1": event_stream_schema(
            "WorkflowHistoryEventStream",
            WorkflowHistoryEventModel.model_json_schema(),
        ),
        "workflow-cancellation-request-v1": WorkflowCancellationRequestModel.model_json_schema(),
        "evaluation-result-envelope-v1": EvaluationResultStateModel.model_json_schema(),
        "proposition-truth-result-v1": PropositionTruthResultModel.model_json_schema(),
        "sdl-lineage-ledger-v1": SDLLineageLedgerModel.model_json_schema(),
        "scientific-completeness-taxonomy-v1": ScientificCompletenessTaxonomyModel.model_json_schema(),
        "scientific-completeness-assessment-v1": ScientificCompletenessAssessmentModel.model_json_schema(),
        "validation-profile-catalog-v1": ValidationProfileCatalogModel.model_json_schema(),
        "validation-basis-disclosure-v1": ValidationBasisDisclosureDocumentModel.model_json_schema(),
    }


def _core_schema_bundle() -> dict[str, dict[str, Any]]:

    return {
        "raes-semantic-invariants-v1": raes_semantic_invariant_profile_schema(),
        "backend-materialization-attestation-v1": MaterializationSubmission.model_json_schema(),
        "backend-runtime-descendants-v1": RuntimeInventoryReport.model_json_schema(),
        "backend-augmentation-scope-v1": AugmentationPreparation.model_json_schema(),
        "materialization-archive-record-v1": MaterializationArchiveRecord.model_json_schema(),
        "scenario-instantiation-request-v1": InstantiationRequestModel.model_json_schema(),
        **_domain_profile_schema_bundle(),
        **transformation_schema_bundle(),
        "semantic-comparison-request-v1": SemanticComparisonRequestModel.model_json_schema(),
        "semantic-comparison-result-v1": SemanticComparisonResultModel.model_json_schema(),
        "authoring-adapter-profile-v1": AuthoringAdapterProfileModel.model_json_schema(),
        "authoring-adapter-vector-v1": AuthoringAdapterVectorModel.model_json_schema(),
        "authoring-adapter-comparison-v1": AuthoringAdapterComparisonModel.model_json_schema(),
        "backend-manifest-v2": BackendManifestV2Model.model_json_schema(),
        "realization-envelope-v1": BackendRealizationEnvelopeModel.model_json_schema(),
        "recursive-realization-constraint-v1": RealizationConstraintDocument.model_json_schema(),
        "backend-realization-preparation-v1": BackendPreparationResponseModel.model_json_schema(),
        "plan-realization-profiles-v1": PlanProfileAuthority.model_json_schema(),
        "observation-demand-v1": ObservationDemandDocument.model_json_schema(),
        "processor-manifest-v2": ProcessorManifestV2Model.model_json_schema(),
        "participant-implementation-manifest-v1": ParticipantImplementationManifestModel.model_json_schema(),
        "participant-implementation-provenance-v1": ParticipantImplementationProvenanceModel.model_json_schema(),
        "concept-families-v1": ConceptFamilyCatalogModel.model_json_schema(),
        "behavioral-relations-v1": BehavioralRelationCatalogModel.model_json_schema(),
        "behavioral-relation-profile-v1": BehavioralRelationProfileModel.model_json_schema(),
        "participant-opacity-analysis-input-v1": ParticipantOpacityAnalysisInputModel.model_json_schema(),
        "participant-opacity-analysis-evidence-v1": ParticipantOpacityAnalysisEvidenceModel.model_json_schema(),
        "participant-opacity-model-check-input-v1": ParticipantOpacityModelCheckInputModel.model_json_schema(),
        "participant-opacity-model-check-evidence-v1": ParticipantOpacityModelCheckEvidenceModel.model_json_schema(),
        "reference-models-v1": ReferenceModelCatalogModel.model_json_schema(),
        "uco-alignment-v1": UcoAlignmentCatalogModel.model_json_schema(),
        "controlled-vocabularies-v1": ControlledVocabularyCatalogModel.model_json_schema(),
        "external-concept-bindings-v1": ExternalConceptBindingDocumentModel.model_json_schema(),
        "semantic-projection-report-v1": semantic_projection.SemanticProjectionReportModel.model_json_schema(),
        "attack-enterprise-tactics-source-v1": AttackEnterpriseTacticsSourceModel.model_json_schema(),
        "atlas-tactics-source-v1": AtlasTacticsSourceModel.model_json_schema(),
        "nist-csf-defensive-categories-source-v1": NistCsfDefensiveCategorySourceModel.model_json_schema(),
        "w3c-activitystreams-activity-types-source-v1": ActivityStreamsActivityTypesSourceModel.model_json_schema(),
        "fipa-communicative-acts-source-v1": FipaCommunicativeActsSourceModel.model_json_schema(),
        "semantic-profile-v1": semantic_profiles.SemanticProfileModel.model_json_schema(),
        "backend-profile-v1": backend_profile_schema(),
        "random-stream-profile-v1": RandomStreamProfileModel.model_json_schema(),
        "participant-information-reconstruction-profile-v1": (
            ParticipantInformationReconstructionProfileModel.model_json_schema()
        ),
        "participant-boundary-flow-policy-v1": ParticipantBoundaryFlowPolicyProfileModel.model_json_schema(),
        "participant-owner-flow-policy-v1": ParticipantOwnerFlowPolicyProfileModel.model_json_schema(),
        "random-stream-vector-v1": RandomStreamVectorModel.model_json_schema(),
        **_experiment_schema_bundle(),
    }


def contract_schemas() -> dict[str, dict[str, Any]]:
    """Return the raw contract schemas that ``raes_contracts`` owns, with their invariant annotations."""

    bundle = {**_core_schema_bundle(), **runtime_schema_bundle()}
    add_raes_invariant(
        bundle["experiment-capture-spec-v1"],
        "capture-media-type-provable",
        "Every required media type must have a registered content-proof path and be supported by its "
        "declared output_contract.",
        validator="raes_contracts.contracts.ExperimentCaptureRequirementModel._validate_capture_requirement",
        inputs=[{"contract_id": "experiment-capture-spec-v1", "instance_path": "#/capture_requirements"}],
    )
    add_raes_invariant(
        bundle["behavioral-relations-v1"],
        "behavioral-relations-reference-resolution",
        "Relation map keys, bibliography references, claim-surface relation references, and worked-example keys "
        "must resolve exactly inside one taxonomy revision.",
        validator="raes_contracts.behavioral_relations.BehavioralRelationCatalogModel",
        inputs=[{"contract_id": "behavioral-relations-v1", "instance_path": "#"}],
    )
    add_raes_invariant(
        bundle["behavioral-relation-profile-v1"],
        "behavioral-relation-profile-local-join",
        "The closed relation-specific parameter variant must match the profile relation, carrier, projection, "
        "finite domains, local refs, limitations, and explicit nonclaims.",
        validator="raes_contracts.behavioral_relation_profiles.BehavioralRelationProfileModel",
        inputs=[
            {
                "contract_id": "behavioral-relation-profile-v1",
                "instance_path": "#",
            }
        ],
    )
    add_raes_invariant(
        bundle["behavioral-relation-profile-v1"],
        "behavioral-relation-profile-claim-resolution",
        "Catalog, profile, carrier, observation projection, and claim coordinates must resolve exactly through "
        "the shared behavioral claim validator.",
        validator="raes_contracts.behavioral_relations.validate_behavioral_claim_binding",
        inputs=[
            {
                "contract_id": "behavioral-relation-profile-v1",
                "instance_path": "#",
            },
            {"contract_id": "behavioral-relations-v1", "instance_path": "#"},
        ],
    )
    add_raes_invariant(
        bundle["participant-opacity-analysis-input-v1"],
        "participant-opacity-finite-carrier-counts",
        "Point ordinals and refs must be unique, and every declared finite count must exactly match the "
        "normalized possible-point carrier.",
        validator="raes_contracts.participant_opacity.ParticipantOpacityAnalysisInputModel",
        inputs=[
            {
                "contract_id": "participant-opacity-analysis-input-v1",
                "instance_path": "#",
            }
        ],
    )
    add_raes_invariant(
        bundle["participant-opacity-analysis-evidence-v1"],
        "participant-opacity-evidence-joins",
        "Profile, normalized model, checker, claim, outcome payload, diagnostics, normalized-input-only "
        "provenance scope, and bounded assurance coordinates must remain digest-bound and mutually consistent.",
        validator="raes_contracts.participant_opacity.ParticipantOpacityAnalysisEvidenceModel",
        inputs=[
            {
                "contract_id": "participant-opacity-analysis-evidence-v1",
                "instance_path": "#",
            },
            {
                "contract_id": "participant-opacity-analysis-input-v1",
                "instance_path": "#",
            },
            {
                "contract_id": "behavioral-relation-profile-v1",
                "instance_path": "#",
            },
        ],
    )
    add_raes_invariant(
        bundle["participant-opacity-model-check-input-v1"],
        "participant-opacity-model-check-graph-joins",
        "State and transition ordinals, refs, endpoints, fixed domains, exact declared counts, assumptions, "
        "and model-check claim coordinates must form one closed canonical transition model.",
        validator="raes_contracts.participant_opacity.ParticipantOpacityModelCheckInputModel",
        inputs=[
            {
                "contract_id": "participant-opacity-model-check-input-v1",
                "instance_path": "#",
            },
            {
                "contract_id": "behavioral-relation-profile-v1",
                "instance_path": "#",
            },
            {"contract_id": "behavioral-relations-v1", "instance_path": "#"},
        ],
    )
    add_raes_invariant(
        bundle["participant-opacity-model-check-evidence-v1"],
        "participant-opacity-model-check-evidence-joins",
        "Exact catalog, profile, model, assumptions, checker, derived carrier, complete coverage, claim, outcome, "
        "diagnostics, and safe counterexample joins must remain digest-bound and mutually consistent.",
        validator="raes_contracts.participant_opacity.ParticipantOpacityModelCheckEvidenceModel",
        inputs=[
            {
                "contract_id": "participant-opacity-model-check-evidence-v1",
                "instance_path": "#",
            },
            {
                "contract_id": "participant-opacity-model-check-input-v1",
                "instance_path": "#",
            },
            {
                "contract_id": "behavioral-relation-profile-v1",
                "instance_path": "#",
            },
            {"contract_id": "behavioral-relations-v1", "instance_path": "#"},
        ],
    )
    add_raes_invariant(
        bundle["experiment-study-v1"],
        "study-behavioral-claim-catalog-resolution",
        "Every study behavioral claim must resolve against the canonical taxonomy revision, include a required "
        "observation projection, and keep bounded evidence out of universal quantifiers.",
        validator="raes_contracts.behavioral_relations.validate_behavioral_claim_binding",
        inputs=[
            {"contract_id": "experiment-study-v1", "instance_path": "#/behavioral_claims"},
            {"contract_id": "behavioral-relations-v1", "instance_path": "#"},
        ],
    )
    add_raes_invariant(
        bundle["scientific-completeness-taxonomy-v1"],
        "scientific-completeness-taxonomy-rectangular",
        "Concern and profile ids must be unique, and every profile disposition "
        "map must exactly cover the taxonomy concern set.",
        validator="raes_contracts.scientific_completeness.ScientificCompletenessTaxonomyModel",
        inputs=[{"contract_id": "scientific-completeness-taxonomy-v1", "instance_path": "#"}],
    )
    add_raes_invariant(
        bundle["scientific-completeness-taxonomy-v1"],
        "scientific-completeness-behavioral-claim-resolution",
        "Each profile must carry resolved behavioral claim bindings and disjoint, catalog-resolved nonclaimed "
        "relation ids.",
        validator="raes_contracts.scientific_completeness.CompletenessProfileModel.validate_behavioral_claims",
        inputs=[
            {"contract_id": "scientific-completeness-taxonomy-v1", "instance_path": "#/profiles"},
            {"contract_id": "behavioral-relations-v1", "instance_path": "#"},
        ],
    )
    add_raes_invariant(
        bundle["scientific-completeness-assessment-v1"],
        "scientific-completeness-assessment-status-evidence",
        "Concern ids must be unique and each delivery status must carry its "
        "required executable evidence, external binding, issue refs, or "
        "exclusion rationale.",
        validator="raes_contracts.scientific_completeness.ScientificCompletenessAssessmentModel",
        inputs=[{"contract_id": "scientific-completeness-assessment-v1", "instance_path": "#"}],
    )
    add_raes_invariant(
        bundle["runtime-fact-binding-plane-v1"],
        "runtime-fact-binding-references-resolve",
        "Every fact version resolves to a declaration, every binding event resolves to its compiled sink and "
        "optional immutable fact version with matching scope, sensitivity, provenance, redaction, and sink policy, "
        "and every projection exactly matches the immutable version it discloses.",
        validator="raes_contracts.contracts.runtime_facts.RuntimeFactBindingPlaneModel._validate_references",
        inputs=[{"contract_id": "runtime-fact-binding-plane-v1", "instance_path": "#"}],
    )
    add_raes_invariant(
        bundle["scientific-completeness-assessment-v1"],
        "scientific-completeness-taxonomy-assessment-join",
        "Assessment family, taxonomy revision, and concern ids must exactly "
        "match the joined taxonomy before completeness is computed.",
        validator="raes_contracts.scientific_completeness.evaluate_profile_completeness",
        inputs=[
            {"contract_id": "scientific-completeness-taxonomy-v1", "instance_path": "#"},
            {"contract_id": "scientific-completeness-assessment-v1", "instance_path": "#"},
        ],
    )
    add_raes_invariant(
        bundle["validation-profile-catalog-v1"],
        "validation-profile-catalog-reference-integrity",
        "Strength ranks and term ids must be unique, profile identities must "
        "be unique, required and optional gates must be disjoint, and every "
        "profile reference must resolve within the catalog.",
        validator=("raes_contracts.validation_profiles.ValidationProfileCatalogModel"),
        inputs=[
            {
                "contract_id": "validation-profile-catalog-v1",
                "instance_path": "#",
            }
        ],
    )
    return bundle


__all__ = ["contract_schemas"]

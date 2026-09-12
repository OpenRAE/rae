"""Published JSON Schema bundle assembly for external RAES contracts."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from typing import Any

from raes.canonical import InstantiatedScenarioSnapshot
from raes.scenario import InstantiatedScenario, Scenario

from raes_contracts.artifact_requirements import ArtifactRequirementContractModel
from raes_contracts.observation_demand import ObservationDemandDocument

from . import semantic_profiles, semantic_projection
from .admitted_trial_plan import AdmittedTrialPlanModel
from .batch_execution import BatchExecutionReceiptModel
from .bundle_runtime import _runtime_schema_bundle
from .catalogs import (
    ConceptFamilyCatalogModel,
    ReferenceModelCatalogModel,
    UcoAlignmentCatalogModel,
)
from .execution_state import (
    EvaluationResultStateModel,
    InstantiationRequestModel,
    PropositionTruthResultModel,
    WorkflowCancellationRequestModel,
    WorkflowExecutionStateModel,
    WorkflowHistoryEventModel,
)
from .experiment_apparatus import ExperimentApparatusContextModel, ExperimentTaskModel
from .experiment_bindings import (
    ExperimentBindingDescriptorSetModel,
)
from .experiment_capture import ExperimentCaptureSpecModel
from .experiment_evidence import ExperimentDerivedMeasureModel, ExperimentEvidenceRecordModel
from .experiment_run import ExperimentRunModel
from .experiment_spec import ExperimentSpecModel, ExperimentStudyModel
from .external_concept_bindings import ExternalConceptBindingDocumentModel
from .manifests import ProcessorManifestV2Model
from .participant_flow_control import (
    ParticipantBoundaryFlowPolicyProfileModel,
)
from .participant_information_state import (
    ParticipantInformationReconstructionProfileModel,
)
from .participant_manifests import (
    BackendManifestV2Model,
    ParticipantImplementationManifestModel,
    ParticipantImplementationProvenanceModel,
)
from .random_stream import RandomStreamProfileModel, RandomStreamVectorModel
from .realization_plans import (
    EvaluationPlanModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
    RuntimeSnapshotEnvelopeModel,
)
from .reusable_assets import (
    _backend_profile_schema_for_bundle,
    _event_stream_schema,
)
from .schema_constraints import (
    _attach_compiled_address_map_constraints,
    _attach_instantiation_invariants,
    _attach_json_schema_metadata,
    _attach_plan_identity_constraints,
    _attach_sdl_identifier_constraints,
    _raes_semantic_invariant_profile_schema_for_bundle,
    _validate_raes_semantic_invariant_annotations,
)
from .schema_invariants import (
    _add_raes_invariant,
    _attach_experiment_datetime_invariants,
    _attach_initial_service_state_invariants,
    _attach_raes_semantic_profile,
    _attach_stateful_resource_invariants,
)
from .time_model import RealizedTimeModelProvenanceModel, TimeModelDeclarationModel, TimeRuntimeStateModel
from .transformation_schemas import transformation_schema_bundle
from .trial_cleanup import SchedulerIsolationProofModel, TrialCleanupPlanModel, TrialCleanupReceiptModel
from .validation_disclosure import ValidationBasisDisclosureDocumentModel
from .vocabulary_sources import (
    ActivityStreamsActivityTypesSourceModel,
    AtlasTacticsSourceModel,
    AttackEnterpriseTacticsSourceModel,
    ControlledVocabularyCatalogModel,
    FipaCommunicativeActsSourceModel,
    NistCsfDefensiveCategorySourceModel,
)


def _domain_profile_schema_bundle() -> dict[str, dict[str, Any]]:
    from raes_contracts.domain_profiles import (
        DomainProfileAdmissionPolicyModel,
        DomainProfileBindingModel,
        DomainProfileDefinitionModel,
        DomainProfileResolutionContextModel,
        DomainProfileSupportDeclarationModel,
    )

    return {
        "domain-profile-definition-v1": DomainProfileDefinitionModel.model_json_schema(),
        "domain-profile-binding-v1": DomainProfileBindingModel.model_json_schema(),
        "domain-profile-resolution-context-v1": DomainProfileResolutionContextModel.model_json_schema(),
        "domain-profile-support-declaration-v1": DomainProfileSupportDeclarationModel.model_json_schema(),
        "domain-profile-admission-policy-v1": DomainProfileAdmissionPolicyModel.model_json_schema(),
    }


def _experiment_schema_bundle() -> dict[str, dict[str, Any]]:
    """Experiment, trial, time, and runtime-plan contract schemas."""

    from ..provenance import SDLLineageLedgerModel
    from ..scientific_completeness import (
        ScientificCompletenessAssessmentModel,
        ScientificCompletenessTaxonomyModel,
    )
    from ..validation_profiles import ValidationProfileCatalogModel

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
        "workflow-history-event-stream-v1": _event_stream_schema(
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
    from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel
    from raes_contracts.realization_structure import RealizationConstraintDocument
    from raes_contracts.semantic_comparison import SemanticComparisonRequestModel, SemanticComparisonResultModel

    from ..behavioral_relation_profiles import BehavioralRelationProfileModel
    from ..behavioral_relations import BehavioralRelationCatalogModel
    from ..exploit_path import ExploitPathAnalysisEvidenceModel
    from ..participant_opacity import (
        ParticipantOpacityAnalysisEvidenceModel,
        ParticipantOpacityAnalysisInputModel,
        ParticipantOpacityModelCheckEvidenceModel,
        ParticipantOpacityModelCheckInputModel,
    )
    from ..realization_profiles import PlanProfileAuthority
    from ..satisfiability import ScenarioSatisfiabilityEvidenceModel
    from .backend_preparation import BackendPreparationResponseModel

    return {
        "raes-semantic-invariants-v1": _raes_semantic_invariant_profile_schema_for_bundle(),
        "sdl-authoring-input-v1": Scenario.model_json_schema(),
        "instantiated-scenario-v1": InstantiatedScenario.model_json_schema(),
        "instantiated-scenario-snapshot-v1": InstantiatedScenarioSnapshot.model_json_schema(),
        "scenario-instantiation-request-v1": InstantiationRequestModel.model_json_schema(),
        "artifact-requirement-v1": ArtifactRequirementContractModel.model_json_schema(),
        **_domain_profile_schema_bundle(),
        **transformation_schema_bundle(),
        "semantic-comparison-request-v1": SemanticComparisonRequestModel.model_json_schema(),
        "semantic-comparison-result-v1": SemanticComparisonResultModel.model_json_schema(),
        "exploit-path-analysis-evidence-v1": ExploitPathAnalysisEvidenceModel.model_json_schema(),
        "scenario-satisfiability-evidence-v1": ScenarioSatisfiabilityEvidenceModel.model_json_schema(),
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
        "backend-profile-v1": _backend_profile_schema_for_bundle(),
        "random-stream-profile-v1": RandomStreamProfileModel.model_json_schema(),
        "participant-information-reconstruction-profile-v1": (
            ParticipantInformationReconstructionProfileModel.model_json_schema()
        ),
        "participant-boundary-flow-policy-v1": ParticipantBoundaryFlowPolicyProfileModel.model_json_schema(),
        "random-stream-vector-v1": RandomStreamVectorModel.model_json_schema(),
        **_experiment_schema_bundle(),
    }


def _raw_schema_bundle() -> dict[str, dict[str, Any]]:
    return {**_core_schema_bundle(), **_runtime_schema_bundle()}


@cache
def _schema_bundle_template() -> dict[str, dict[str, Any]]:  # NOSONAR
    """Build the immutable-in-practice template used by :func:`schema_bundle`."""

    bundle = _raw_schema_bundle()
    _add_raes_invariant(
        bundle["behavioral-relations-v1"],
        "behavioral-relations-reference-resolution",
        "Relation map keys, bibliography references, claim-surface relation references, and worked-example keys "
        "must resolve exactly inside one taxonomy revision.",
        validator="raes_contracts.behavioral_relations.BehavioralRelationCatalogModel",
        inputs=[{"contract_id": "behavioral-relations-v1", "instance_path": "#"}],
    )
    _add_raes_invariant(
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
    _add_raes_invariant(
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
    _add_raes_invariant(
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
    _add_raes_invariant(
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
    _add_raes_invariant(
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
    _add_raes_invariant(
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
    _add_raes_invariant(
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
    _add_raes_invariant(
        bundle["scientific-completeness-taxonomy-v1"],
        "scientific-completeness-taxonomy-rectangular",
        "Concern and profile ids must be unique, and every profile disposition "
        "map must exactly cover the taxonomy concern set.",
        validator="raes_contracts.scientific_completeness.ScientificCompletenessTaxonomyModel",
        inputs=[{"contract_id": "scientific-completeness-taxonomy-v1", "instance_path": "#"}],
    )
    _add_raes_invariant(
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
    _add_raes_invariant(
        bundle["scientific-completeness-assessment-v1"],
        "scientific-completeness-assessment-status-evidence",
        "Concern ids must be unique and each delivery status must carry its "
        "required executable evidence, external binding, issue refs, or "
        "exclusion rationale.",
        validator="raes_contracts.scientific_completeness.ScientificCompletenessAssessmentModel",
        inputs=[{"contract_id": "scientific-completeness-assessment-v1", "instance_path": "#"}],
    )
    _add_raes_invariant(
        bundle["runtime-fact-binding-plane-v1"],
        "runtime-fact-binding-references-resolve",
        "Every fact version resolves to a declaration, every binding event resolves to its compiled sink and "
        "optional immutable fact version with matching scope, sensitivity, provenance, redaction, and sink policy, "
        "and every projection exactly matches the immutable version it discloses.",
        validator="raes_contracts.contracts.runtime_facts.RuntimeFactBindingPlaneModel._validate_references",
        inputs=[{"contract_id": "runtime-fact-binding-plane-v1", "instance_path": "#"}],
    )
    _add_raes_invariant(
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
    _add_raes_invariant(
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
    for contract_id, json_schema in bundle.items():
        _attach_sdl_identifier_constraints(contract_id, json_schema)
        _attach_instantiation_invariants(contract_id, json_schema)
        _attach_experiment_datetime_invariants(contract_id, json_schema)
        _attach_stateful_resource_invariants(contract_id, json_schema)
        _attach_initial_service_state_invariants(contract_id, json_schema)
        _attach_json_schema_metadata(contract_id, json_schema)
        _attach_compiled_address_map_constraints(contract_id, json_schema)
        _attach_plan_identity_constraints(contract_id, json_schema)
        _attach_raes_semantic_profile(contract_id, json_schema)
    known_contract_ids = frozenset(bundle)
    for contract_id, json_schema in bundle.items():
        _validate_raes_semantic_invariant_annotations(
            contract_id=contract_id,
            json_schema=json_schema,
            known_contract_ids=known_contract_ids,
        )
    return bundle


def schema_bundle() -> dict[str, dict[str, Any]]:
    """Return an isolated copy of the repo-published external contract schemas.

    Generating the complete bundle is expensive because it traverses every
    Pydantic contract model and attaches the governed RAES annotations.  The
    generated template is process-stable, so build it once while preserving the
    public function's historical fresh-dictionary semantics for callers.
    """

    return deepcopy(_schema_bundle_template())

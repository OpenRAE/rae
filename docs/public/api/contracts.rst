Shared contracts
================

The ``raes_contracts`` package owns shared data types and checks.
The processor, runtime and backend exchange these values.
A model is data, not a grant to execute work or proof of backend support.

Inputs, defaults and errors
---------------------------

``raes_contracts.contracts`` lists the exported artifact types.
Each model entry shows fields, types and defaults.
Pydantic raises ``pydantic.ValidationError`` when input breaks a field or model rule.
Cross-message checks can raise ``ValueError`` when links or digests do not match.
Neither check proves who produced the data.

Wire format versions differ from the installed package version.
``schema_version`` selects the contract version.
A digest profile, source format or runtime profile has its own name and meaning.
The :doc:`reference conventions <index>` explain model entries without independent narrative descriptions.

Artifact contract exports
-------------------------

This list includes exported types and constants.
An imported member stays visible even when its source module is private.
This keeps the public alias; the private module does not become a public API.
The entries give data shapes and checks, with draft status where it applies.
A draft or a claim of capability does not prove that a backend can execute work.

.. automodule:: raes_contracts.contracts
   :members:
   :exclude-members: BackendOperationBindingModel,
      BackendOperationCapabilitiesModel,
      BackendOperationControlModel,
      BackendOperationRequestModel,
      OperationArtifactReferenceModel,
      OperationBudgetModel,
      OperationEffectScopeModel,
      BackendOperationAcknowledgementModel,
      BackendOperationAdmissionModel,
      BackendOperationControlDispositionModel,
      BackendOperationEffectsModel,
      BackendOperationOutcomeModel,
      BackendOperationProgressModel,
      BackendOperationReconciliationModel,
      BackendOperationResponseModel,
      backend_operation_control_digest,
      backend_operation_request_digest,
      canonical_backend_operation_capabilities_digest,
      require_backend_operation_admission,
      require_backend_execution_policy_admission,
      validate_backend_operation_history,
      validate_backend_operation_response,
      InjectBindingOutcomeModel,
      InjectEventPlacementModel,
      InjectIndependentPlacementModel,
      InjectOccurrenceCorrelationModel,
      InjectOccurrenceModel,
      InjectOccurrenceOutcomeModel,
      InjectOrderModel,
      InjectSchedulePlacementModel,
      InjectTargetBindingModel,
      InjectTriggerRequestModel,
      inject_occurrence_correlation,
      inject_occurrence_digest,
      inject_occurrence_effect,
      inject_occurrence_outcome_digest,
      inject_occurrence_reference,
      inject_retry_key,
      inject_trigger_request_digest,
      require_inject_occurrence_invocation,
      require_inject_trigger_retry,
      validate_inject_occurrence_claims,
      validate_inject_occurrence_correlation,
      validate_inject_occurrence_outcome,
      MixedBackendDeliveryStageModel,
      MixedBackendEdgeBindingModel,
      MixedBackendEdgeTimeRequirementModel,
      MixedBackendExecutionBindingModel,
      MixedBackendExecutionStageModel,
      MixedBackendHandoffBindingModel,
      MixedBackendHandoffStageModel,
      MixedBackendObservationStageModel,
      MixedBackendOwnerReadbackStageModel,
      MixedBackendServiceModel,
      MixedBackendStageContext,
      MixedBackendStageReportModel,
      MixedBackendTimeGrantStageModel,
      MixedBackendTimeRequirementModel,
      mixed_backend_binding_reference,
      established_mixed_backend_state,
      mixed_backend_time_comparison,
      require_mixed_backend_admission,
      require_mixed_backend_request,
      validate_mixed_backend_bindings,
      validate_mixed_backend_stage_reports,
      ArtifactTransformationCheckModel,
      ArtifactTransformationIdentityMapModel,
      ArtifactTransformationKind,
      ArtifactTransformationLossKind,
      ArtifactTransformationLossModel,
      ArtifactTransformationPreservationModel,
      ArtifactTransformationReportModel,
      ArtifactTransformationStatus,
      PreservationOutcome,
      TransformationCheckOutcome
   :imported-members:
   :undoc-members:

Backend protocols
-----------------

``raes_backend_protocols`` declares the interfaces that an admitted backend implements.
The exports cover topology binding, trial units, operation supervision and mixed-backend services.
A protocol does not install a backend.
The conformance runner checks finite cases.
A passing result does not prove all runtime behavior.
See :doc:`backend tasks <../backends>` for the supported integration route.

.. automodule:: raes_backend_protocols
   :members:
   :imported-members:
   :undoc-members:

Conformance runners
-------------------

.. automodule:: raes_conformance.conformance
   :members:
   :imported-members:

Diagnostics
-----------

.. automodule:: raes_contracts.diagnostics
   :members:

Artifact transformation reports
-------------------------------

.. automodule:: raes_contracts.contracts.artifact_transformations
   :members:

Planning
--------

.. automodule:: raes_contracts.planning
   :members:

Runtime state
-------------

.. automodule:: raes_contracts.runtime_state
   :members:

Workflow results
----------------

.. automodule:: raes_contracts.workflow
   :members:

Evaluation results
------------------

.. automodule:: raes_contracts.evaluation
   :members:

Participant episodes
--------------------

.. automodule:: raes_contracts.participant_episode
   :members:

Participant implementation manifests
------------------------------------

``ParticipantImplementationManifestModel`` and
``ParticipantImplementationProvenanceModel`` live in
``raes_contracts.contracts`` with the other published contract models. The
manifest gives its identity, capabilities and compatible contracts.
It also gives decision-surface modes, tool-affordance needs and constraints.
The provenance record keeps the implementation, manifest and configuration reference selected for a run.
It also keeps the participant contract versions and decision-surface exposure policy.

Mixed-backend execution and readback
------------------------------------

These optional bindings and stage reports describe one admitted mixed edge or native handoff.
The backend operation protocol exchanges them.
They grant no authority, and the shared runtime does not read them.

.. automodule:: raes_contracts.contracts.mixed_backend_binding
   :members:

.. automodule:: raes_contracts.contracts.mixed_backend_stages
   :members:

.. automodule:: raes_contracts.contracts.mixed_backend_validation
   :members:

.. automodule:: raes_contracts.contracts.mixed_backend_transcript
   :members:

.. automodule:: raes_backend_protocols.mixed_backend
   :members:

Backend operation supervision
-----------------------------

The optional backend protocol reports evidence for one admitted invocation.
The shared runtime retains authorization, scenario execution and terminal state.

.. automodule:: raes_contracts.contracts.backend_operation
   :members:

.. automodule:: raes_contracts.contracts.backend_operation_response
   :members:

.. automodule:: raes_contracts.contracts.backend_operation_validation
   :members:

.. automodule:: raes_backend_protocols.operation_supervision
   :members:

External inject triggers, occurrences and readback
--------------------------------------------------

These draft ADR-112 types carry an external inject request and its claimed occurrence.
They also carry readback for each binding and participant correlation.
They grant no trigger authority and do not execute an inject.

.. automodule:: raes_contracts.contracts.inject_occurrence
   :members:

.. automodule:: raes_contracts.contracts.inject_occurrence_outcome
   :members:

Constants and type aliases
--------------------------

These entries retain the exported values and type definitions.
Version constants identify data formats, not the installed package version.
Type aliases give accepted shapes; they do not create another wire contract.
Literal values and callback types need no separate model narrative.

.. autodata:: raes_contracts.contracts.BACKEND_OPERATION_REQUEST_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.BACKEND_OPERATION_CAPABILITIES_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.BACKEND_OPERATION_CONTROL_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.BACKEND_OPERATION_RESPONSE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.BACKEND_OPERATION_CONTRACT_IDS

.. autodata:: raes_contracts.contracts.OPERATION_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.INJECT_TRIGGER_REQUEST_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.INJECT_OCCURRENCE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.INJECT_OCCURRENCE_OUTCOME_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.INJECT_OCCURRENCE_CORRELATION_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS

.. autodata:: raes_contracts.contracts.ParticipantControlContextResolver

.. autodata:: raes_contracts.contracts.ParticipantControlContextResolverV2

.. autodata:: raes_contracts.contracts.PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE

.. autodata:: raes_contracts.contracts.PARTICIPANT_CONTROL_VALIDITY_BOUNDS_MISMATCH

.. autodata:: raes_contracts.contracts.MIXED_COMPOSITION_CONTRACT_ID

.. autodata:: raes_contracts.contracts.MIXED_BACKEND_CONTRACT_IDS

.. autodata:: raes_contracts.contracts.MIXED_BACKEND_EXECUTION_BINDING_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.MIXED_BACKEND_STAGE_REPORT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ACTIVITYSTREAMS_ACTIVITY_TYPES_SOURCE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ATTACK_ENTERPRISE_TACTICS_SOURCE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ATLAS_TACTICS_SOURCE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ASSOCIATED_ARTIFACT_MANIFEST_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ARTIFACT_REQUIREMENT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ARTIFACT_TRANSFORMATION_REPORT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.SDL_CANDIDATE_SYNTHESIS_INPUT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.SDL_CANDIDATE_SYNTHESIS_PROFILE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.SDL_CANDIDATE_SYNTHESIS_RECORD_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.SourceAssertion

.. autodata:: raes_contracts.contracts.AssociatedArtifactSetDigestString

.. autodata:: raes_contracts.contracts.BACKEND_MANIFEST_V2_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.BEHAVIORAL_RELATION_PROFILE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.BehavioralRelationId

.. autodata:: raes_contracts.contracts.BehavioralTaxonomyRevision

.. autodata:: raes_contracts.contracts.CONCEPT_FAMILIES_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ConceptFamilyId

.. autodata:: raes_contracts.contracts.EXTERNAL_CONCEPT_BINDINGS_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.FIPA_COMMUNICATIVE_ACTS_SOURCE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.CONTROLLED_VOCABULARIES_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ControlledVocabularyTermId

.. autodata:: raes_contracts.contracts.DifficultyCondition

.. autodata:: raes_contracts.contracts.DifficultyThresholdValue

.. autodata:: raes_contracts.contracts.ADAPTIVE_THRESHOLD_PROFILE_DIGEST

.. autodata:: raes_contracts.contracts.NIST_CSF_DEFENSIVE_CATEGORIES_SOURCE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EXPERIMENT_APPARATUS_CONTEXT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EXPERIMENT_AUTHORING_INPUT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EXPERIMENT_BINDING_DESCRIPTORS_V1_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EXPERIMENT_CAPTURE_SPEC_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EXPERIMENT_DERIVED_MEASURE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EXPERIMENT_EVIDENCE_RECORD_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EXPERIMENT_RUN_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EXPERIMENT_STUDY_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EXPERIMENT_TASK_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.EVALUATION_STATE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.PARTICIPANT_BOUNDARY_FLOW_POLICY_V1_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.PARTICIPANT_FLOW_CONTROL_RELATION_V1_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.PARTICIPANT_IMPLEMENTATION_MANIFEST_V1_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.PARTICIPANT_IMPLEMENTATION_PROVENANCE_V1_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.PARTICIPANT_CONFIGURATION_RESULT_V1_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ParticipantFlowControlContextResolver

.. autodata:: raes_contracts.contracts.ParticipantDecisionSurfaceDerivationAnchorV2Model

.. autodata:: raes_contracts.contracts.ParticipantDecisionSurfaceStateCutModel

.. autodata:: raes_contracts.contracts.ParticipantDecisionSurfaceStateCutOrderModel

.. autodata:: raes_contracts.contracts.PARTICIPANT_OPACITY_ANALYSIS_EVIDENCE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.PARTICIPANT_OPACITY_ANALYSIS_INPUT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ParticipantInformationStateContextResolver

.. autodata:: raes_contracts.contracts.VIEW_SCOPE_PROJECTED_FIELDS

.. autodata:: raes_contracts.contracts.PROCESSOR_MANIFEST_V2_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.RANDOM_STREAM_DRAW_PURPOSE_SCOPE

.. autodata:: raes_contracts.contracts.RANDOM_STREAM_PROFILE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.RANDOM_STREAM_VECTOR_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.RandomDrawOutcomeModel

.. autodata:: raes_contracts.contracts.RootEntropyModel

.. autodata:: raes_contracts.contracts.REFERENCE_MODELS_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.REUSABLE_ASSET_EVIDENCE_CLASSES

.. autodata:: raes_contracts.contracts.REUSABLE_ASSET_FAMILIES

.. autodata:: raes_contracts.contracts.REUSABLE_ASSET_TRUST_POLICY_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.RUNTIME_SNAPSHOT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.RUNTIME_FACT_BINDING_PLANE_V1_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.SCENARIO_INSTANTIATION_REQUEST_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.SEMANTIC_PROFILE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.SEMANTIC_PROJECTION_REPORT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.UCO_ALIGNMENT_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.WORKFLOW_CANCELLATION_REQUEST_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.WORKFLOW_STATE_SCHEMA_VERSION

.. autodata:: raes_contracts.contracts.ProcessorPlanKind

.. autodata:: raes_conformance.conformance.MIXED_BACKEND_CASES

.. autodata:: raes_conformance.conformance.BackendProfileSelector

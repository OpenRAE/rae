Processor layer
===============

The ``raes_processor`` package compiles SDL and plans changes against a backend manifest.
It returns models and diagnostics.
Live execution belongs to ``raes_runtime``; shared boundary types belong to ``raes_contracts``.

Inputs, results and failures
----------------------------

``compile_scenario_runtime_model`` accepts authoring, instantiated or materialized input.
For authoring input, it binds the supplied parameters and profile before it compiles the scenario.
``compile_runtime_model`` also accepts authoring input and instantiates it with defaults.
Both return ``RuntimeModel``; the model can contain error diagnostics.
Input checks and variable binding can raise SDL or shared invalid-input errors.

``plan`` accepts a compiled model, backend manifest and optional base snapshot.
It returns ``ExecutionPlan`` with provisioning, orchestration, evaluation and diagnostic results.
An absent base snapshot represents empty prior state.
Missing capability and ordering failures can appear as diagnostics rather than raised errors.
The result's validity property states whether the plan has error diagnostics.

``ReferenceProcessor.realize`` and ``run_reference_processor`` parse, compile and plan the input.
Text input means SDL text; a filesystem input must be a ``Path``.
The result is ``ReferenceProcessorResult`` with the runtime model, execution plan and combined diagnostics.
File-backed imports can acquire modules during parsing.
These functions do not execute the plan or contact a realization backend.

Analysis uses explicit governed profiles.
An unsupported result is not a satisfiability or exploit-path conclusion.
The :doc:`command reference <cli>` gives the analysis commands and their distinct exit meanings.

.. currentmodule:: raes_processor

Public API
----------

.. automodule:: raes_processor
   :members:
   :undoc-members:

Compiler
--------

.. automodule:: raes_processor.compiler
   :members:
   :imported-members:

Constants and type aliases
--------------------------

These entries retain the exported values and type definitions.
Version constants identify data formats, not the installed package version.
Type aliases give accepted shapes; they do not create another wire contract.
Literal values and callback types need no separate model narrative.

.. autodata:: raes_processor.models.EVALUATION_STATE_SCHEMA_VERSION

.. autodata:: raes_processor.models.OPERATION_SCHEMA_VERSION

.. autodata:: raes_processor.models.PARTICIPANT_EPISODE_STATE_SCHEMA_VERSION

.. autodata:: raes_processor.models.RUNTIME_SNAPSHOT_SCHEMA_VERSION

.. autodata:: raes_processor.models.WORKFLOW_STATE_SCHEMA_VERSION

.. autodata:: raes_processor.reference.ScenarioInput

.. autodata:: raes_processor.exploit_path.ANALYSIS_PROFILE

.. autodata:: raes_processor.satisfiability.ANALYSIS_PROFILE


Reference processor
-------------------

.. automodule:: raes_processor.reference
   :members:
   :undoc-members:

Processor models
----------------

The ``raes_processor.models`` facade exports compiled types and aliases kept for existing callers.
Its entries include imported types and exports that have no docstring.
The subdomain entries below retain their original reference addresses.

.. automodule:: raes_processor.models
   :members:
   :exclude-members: AccountPlacement,
      ApplyResult,
      AssertionRuntime,
      ChangeAction,
      CompiledCapabilityConstraint,
      ConditionBinding,
      ContentPlacement,
      ServiceContentMaterializationBinding,
      ServiceSearchIndexSchemaMaterializationBinding,
      DomainControllerPlacement,
      GeneratedArtifactRuntime,
      Diagnostic,
      EvaluationExecutionContract,
      EvaluationExecutionState,
      EvaluationHistoryEvent,
      EvaluationHistoryEventType,
      EvaluationOp,
      EvaluationPlan,
      EvaluationResultContract,
      EvaluationResultStatus,
      EventRuntime,
      ExecutionPlan,
      PlanningContext,
      FeatureBinding,
      InjectBinding,
      InjectRuntime,
      NetworkRuntime,
      NodeRuntime,
      ObjectiveRuntime,
      ObjectiveWindowReferenceRuntime,
      MixedControlControllerStateRuntime,
      MixedControlDispositionRulesRuntime,
      MixedControlTransitionRuntime,
      OperationReceipt,
      OperationAdmissionContext,
      OperationKind,
      OperationState,
      OperationStatus,
      OrchestrationOp,
      OrchestrationPlan,
      ParticipantActionContractRuntime,
      PersistentVolumeRuntime,
      ParticipantActionEffectResult,
      ParticipantActionPreconditionResult,
      ParticipantActionResult,
      ParticipantAttributionCandidate,
      ParticipantAttributionEdge,
      ParticipantAttributionEvidenceBasis,
      ParticipantAttributionOrderingBasis,
      ParticipantBehaviorHistoryEvent,
      ParticipantBehaviorRuntime,
      ParticipantBehaviorSpecificationRuntime,
      ParticipantInjectDeliveryRuntime,
      ParticipantAutonomousExecutionRuntime,
      ParticipantExecutionBindingRuntime,
      ParticipantInvocationToolBindingRuntime,
      ParticipantInteractiveAccessRuntime,
      ParticipantEpisodeControlAction,
      ParticipantEpisodeExecutionState,
      ParticipantEpisodeHistoryEvent,
      ParticipantEpisodeHistoryEventType,
      ParticipantEpisodeInitializeRequest,
      ParticipantEpisodeResetRequest,
      ParticipantEpisodeRestartRequest,
      ParticipantEpisodeStatus,
      ParticipantEpisodeTerminalReason,
      ParticipantEpisodeTerminateRequest,
      ParticipantHistoryAddressScope,
      ParticipantObservationBoundaryRuntime,
      ParticipantToolAffordanceRuntime,
      ParticipantOutcomeInterpretationRecord,
      ParticipantOutcomeInterpretationRuleRuntime,
      ParticipantOutcomeSourceRecord,
      ParticipantOutcomeTargetRecord,
      ParticipantTemporalRuntimeContext,
      ParticipantTemporalStateTransition,
      PlanOperation,
      PlannedResource,
      PropositionRuntime,
      ProvisionOp,
      ProvisioningPlan,
      RealizationProvenanceEntry,
      ResolvedResource,
      RuntimeDomain,
      RuntimeModel,
      RuntimeSnapshot,
      RuntimeSnapshotEnvelope,
      RuntimeTemplate,
      ScriptRuntime,
      Severity,
      SnapshotEntry,
      StoryRuntime,
      WorkflowCancellationRequest,
      WorkflowCompensationStatus,
      WorkflowExecutionContract,
      WorkflowExecutionState,
      WorkflowHistoryEvent,
      WorkflowHistoryEventType,
      WorkflowPredicateRuntime,
      WorkflowResultContract,
      WorkflowRuntime,
      WorkflowStatus,
      WorkflowStepExecutionState,
      WorkflowStepLifecycle,
      WorkflowStepOutcome,
      WorkflowStepRuntime,
      WorkflowStepStatePredicateRuntime,
      WorkflowSwitchCaseRuntime,
      iter_participant_behavior_history_violations,
      iter_participant_behavior_joint_action_violations,
      iter_participant_episode_snapshot_violations,
      iter_participant_temporal_state_machine_violations,
      map_backend_diagnostic_to_participant_failure,
      resource_payload,
      validate_evaluation_result,
      validate_participant_action_result_contract,
      validate_participant_outcome_interpretation_record
   :imported-members:
   :undoc-members:

.. automodule:: raes_processor.models.resources
   :members:

.. automodule:: raes_processor.models.behavior_resources
   :members:

.. automodule:: raes_processor.models.action_results
   :members:

.. automodule:: raes_processor.models.attribution
   :members:

.. automodule:: raes_processor.models.outcome
   :members:

.. automodule:: raes_processor.models.outcome_interpretation_validation
   :members:

.. automodule:: raes_processor.models.temporal
   :members:

.. automodule:: raes_processor.models.history_event
   :members:

.. automodule:: raes_processor.models.behavior_history_violations
   :members:

.. automodule:: raes_processor.models.runtime_model
   :members:

Manifest authority
------------------

.. automodule:: raes_processor.manifest
   :members:

Planner
-------

.. automodule:: raes_processor.planner
   :members:
   :imported-members:

Capabilities
------------

.. automodule:: raes_processor.capabilities
   :members:

Exploit-path analysis
---------------------

.. automodule:: raes_processor.exploit_path
   :members:
   :imported-members:

Satisfiability analysis
-----------------------

.. automodule:: raes_processor.satisfiability
   :members:
   :imported-members:

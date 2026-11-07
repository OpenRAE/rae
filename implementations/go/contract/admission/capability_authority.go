package admission

// Authority values follow the published enums and reference capability joins.
func supportedManifestContracts(key string) []string {
	switch key {
	case kindBackend:
		return []string{"artifact-requirement-v1", "backend-augmentation-scope-v1", termBackendManifestV2, termBackendMaterializationAttestationV1, termBackendOperationCapabilitiesV1, termBackendOperationControlV1, termBackendOperationRequestV1, termBackendOperationResponseV1, "backend-realization-preparation-v1", termBackendRuntimeDescendantsV1, "evaluation-history-event-stream-v1", termEvaluationPlanV1, "evaluation-result-envelope-v1", termExperimentBindingDescriptorsV1, "experiment-capture-spec-v1", "experiment-derived-measure-v1", termExperimentEvidenceRecordV1, "experiment-run-v1", termInjectOccurrenceOutcomeV1, "inject-occurrence-v1", termMixedBackendExecutionBindingV1, termMixedBackendStageReportV1, termOperationReceiptV1, termOperationStatusV1, termOrchestrationPlanV1, termParticipantBehaviorHistoryEventStreamV1, termParticipantControlEvaluationV1, "participant-control-evaluation-v2", termParticipantControlOccurrenceV1, "participant-control-selection-v1", "participant-control-selection-v2", termParticipantCrossingOccurrenceV1, termParticipantEpisodeHistoryEventStreamV1, termParticipantEpisodeStateEnvelopeV1, termParticipantExecutionBindingV1, termParticipantExecutionControlV1, termParticipantExecutionServiceStateV1, termParticipantFlowControlRelationV1, termParticipantJointActionRecordV1, "participant-lifecycle-event-v1", termParticipantObservationEnvelopeV1, "participant-outcome-report-v1", "participant-resource-budget-event-v1", termParticipantResourceBudgetPolicyV1, "participant-resource-budget-state-v1", "participant-resource-pool-capacity-v1", termParticipantSharedStateRecordV1, termParticipantTimeManagementContextV1, "plan-realization-profiles-v1", termPropositionTruthResultV1, termProvisioningPlanV1, termRealizationEnvelopeV1, termRealizedTimeModelV1, termRuntimeSnapshotV1, termTimeModelV1, termTimeRuntimeStateV1, termTrialCleanupPlanV1, termTrialCleanupReceiptV1, "workflow-history-event-stream-v1", "workflow-result-envelope-v1"}
	case termParticipant:
		return []string{termExperimentBindingDescriptorsV1, termParticipantBehaviorHistoryEventStreamV1, "participant-configuration-result-v1", termParticipantDecisionSurfaceV2, termParticipantEpisodeHistoryEventStreamV1, termParticipantEpisodeStateEnvelopeV1, termParticipantImplementationManifestV1, "participant-implementation-provenance-v1"}
	case "processor":
		return []string{"evaluation-history-event-stream-v1", termEvaluationPlanV1, "evaluation-result-envelope-v1", termExperimentBindingDescriptorsV1, termOperationReceiptV1, termOperationStatusV1, termOrchestrationPlanV1, termParticipantBehaviorHistoryEventStreamV1, termParticipantEpisodeHistoryEventStreamV1, termParticipantEpisodeStateEnvelopeV1, termParticipantResourceBudgetPolicyV1, termProcessorManifestV2, termPropositionTruthResultV1, termProvisioningPlanV1, termRuntimeSnapshotV1, termTimeModelV1, "workflow-cancellation-request-v1", "workflow-history-event-stream-v1", "workflow-result-envelope-v1"}
	case "sdl":
		return []string{"sdl-authoring-input-v1"}
	default:
		return nil
	}
}
func participantFeatureContracts(key string) []string {
	switch key {
	case "action_contracts":
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case "attribution_support":
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case "autonomous_execution":
		return []string{termOperationReceiptV1, termOperationStatusV1, termParticipantBehaviorHistoryEventStreamV1, termParticipantExecutionBindingV1, termParticipantExecutionControlV1, termParticipantExecutionServiceStateV1, termParticipantJointActionRecordV1, termParticipantSharedStateRecordV1, termParticipantTimeManagementContextV1, termRuntimeSnapshotV1}
	case "behavior_history":
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case "effects":
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case "failure_classes":
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case "observation_boundaries":
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case "outcome_interpretation":
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case "participant_boundary_flow_resolution":
		return []string{termParticipantCrossingOccurrenceV1, termParticipantFlowControlRelationV1}
	case "participant_declassification":
		return []string{termParticipantCrossingOccurrenceV1}
	case "participant_directed_inject_delivery":
		return []string{termOrchestrationPlanV1, termParticipantCrossingOccurrenceV1}
	case "participant_egress_projection":
		return []string{termParticipantCrossingOccurrenceV1, termParticipantObservationEnvelopeV1}
	case "participant_final_sink_mediation":
		return []string{termParticipantCrossingOccurrenceV1, termParticipantFlowControlRelationV1}
	case "participant_ingress_admission":
		return []string{termParticipantControlOccurrenceV1, termParticipantCrossingOccurrenceV1}
	case "participant_intervention":
		return []string{termParticipantControlOccurrenceV1, termParticipantCrossingOccurrenceV1}
	case "participant_modular_control":
		return []string{termParticipantControlEvaluationV1, "participant-control-selection-v1"}
	case "participant_monitor_topology":
		return []string{termExperimentEvidenceRecordV1}
	case "participant_predicate_opacity":
		return []string{termOperationReceiptV1, termOperationStatusV1, termParticipantBehaviorHistoryEventStreamV1, termParticipantControlOccurrenceV1, termParticipantCrossingOccurrenceV1, termParticipantEpisodeHistoryEventStreamV1, termParticipantEpisodeStateEnvelopeV1, termParticipantObservationEnvelopeV1, termRuntimeSnapshotV1}
	case "participant_processing_role_trust":
		return []string{termParticipantControlOccurrenceV1, termParticipantCrossingOccurrenceV1}
	case "participant_quarantined_processing":
		return []string{termParticipantCrossingOccurrenceV1, termParticipantFlowControlRelationV1}
	case "participant_transformation":
		return []string{termParticipantCrossingOccurrenceV1}
	case termPreconditions:
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case termScopedToolAffordances:
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case "state_transitions":
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case "temporal_contracts":
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	case termToolAffordances:
		return []string{termParticipantBehaviorHistoryEventStreamV1, termRuntimeSnapshotV1}
	default:
		return nil
	}
}
func timeCapabilityTerms(key string) []string {
	switch key {
	case "supported_advancement_modes":
		return []string{advancementDilated, "event_driven", "externally_paced", advancementRealTime, advancementStepped}
	case "supported_authority_kinds":
		return []string{kindBackend, termExternal, "runtime", "system"}
	case "supported_constraint_kinds":
		return []string{constraintCadence, kindDeadline, constraintDuration, constraintPrecedence, termWindow}
	case "supported_domain_kinds":
		return []string{termExternal, "logical", termMonotonic, "simulated", termWallClock}
	case "supported_mapping_kinds":
		return []string{"affine_rational", termIdentity}
	case "supported_replay_behaviors":
		return []string{"restart_from_anchor", "restore_recorded_advances", statusUnsupported}
	case "supported_reset_behaviors":
		return []string{"new_segment_preserve_value", "new_segment_zero", statusUnsupported}
	case "supported_synchronization_modes":
		return []string{termAuthority, "barrier", "conservative", postureNone}
	default:
		return nil
	}
}
func coreDistributionFamily(distribution string) string {
	switch distribution {
	case "debian":
		return termLinux
	case "red-hat-enterprise-linux":
		return termLinux
	case "rocky-linux":
		return termLinux
	case "solaris":
		return termOther
	case "ubuntu":
		return termLinux
	case "windows-client":
		return termWindows
	case "windows-server":
		return termWindows
	default:
		return ""
	}
}

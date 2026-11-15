package admission

// experimentFactoryValues supplies fresh native constructor defaults.
// Published schema instances, rather than caller names, select each model.
func experimentFactoryValues(model string) map[string]any {
	var raw string
	switch model {
	case modelTrialApparatus:
		raw = `{"capability_refs":[],"participant_manifest_refs":[]}`
	case modelTrialMixedApparatus:
		raw = `{"participant_manifest_refs":[]}`
	case modelAdmittedTrialEntry:
		raw = `{"bindings":[],"participant_configurations":[],"selections":[],"stochastic_draws":[]}`
	case "AdmittedTrialPlanAdmissionModel":
		raw = `{"diagnostics":[],"limitations":[]}`
	case modelTrialInputRefs:
		raw = `{"capture_spec_refs":[],"mixed_composition_profile_refs":[]}`
	case modelAdmittedTrialPlan:
		raw = `{"stochastic_controls":{}}`
	case "BehavioralClaimBindingModel", "ExperimentRealizedFormDisclosureModel", "ExperimentResultSummaryModel":
		raw = `{"evidence_refs":[]}`
	case "CleanStateRequirementModel":
		raw = `{"verification_probe_refs":[]}`
	case "CleanupObligationModel":
		raw = `{"compensation_refs":[],"depends_on":[],"verification_probe_refs":[]}`
	case termCleanupObligationResultModel:
		raw = `{"evidence_refs":[],"residual_state_refs":[]}`
	case "DifficultyDecisionRecordModel":
		raw = `{"affected_refs":[],"observation_refs":[]}`
	case "DifficultyInterventionRecordModel":
		raw = `{"evidence_refs":[],"occurrence_refs":[]}`
	case "DifficultyPolicyModel":
		raw = `{"actions":{},"observation_sources":{},"threshold_rules":{}}`
	case "DifficultyRunProvenanceModel":
		raw = `{"decisions":[],"interventions":[]}`
	case "DifficultyVariantModel":
		raw = `{"action_refs":[],"scaffold_refs":[],"selection_policy_refs":[]}`
	case "ExecutionRetryPolicyModel":
		raw = `{"compensation_refs":[],"reset_obligation_refs":[]}`
	case "ExperimentApparatusComponentModel":
		raw = `{"compatibility_refs":[],"limitations":[]}`
	case "ExperimentApparatusConstraintModel":
		raw = `{"allowed_backend_refs":[],"allowed_processor_refs":[],"notes":[],"required_capabilities":[],"required_manifest_refs":[]}`
	case termExperimentArtifactRefModel:
		raw = `{"satisfies_refs":[]}`
	case "ExperimentAttemptAccountingModel":
		raw = `{"evidence_record_refs":[],"evidence_records":[],"operation_refs":[]}`
	case "ExperimentAugmentationDisclosureModel":
		raw = `{"affected_refs":[],"evidence_refs":[],"markings":[],"notes":[]}`
	case "ExperimentCaptureRequirementModel":
		raw = `{"notes":[],"required_artifact_roles":[]}`
	case "ExperimentCaptureSpecModel":
		raw = `{"artifact_refs":[],"validity_notes":[]}`
	case termExperimentConditionAssignmentModel:
		raw = `{"required_bindings":[],"required_parameters":[],"required_refs":[],"required_selections":[]}`
	case "ExperimentDerivedMeasureMethodModel", "ExperimentRedVariantSelectionModel":
		raw = `{"parameters":[]}`
	case "ExperimentDerivedMeasureModel":
		raw = `{"limitations":[],"provenance_refs":[]}`
	case "ExperimentEnumerateSelectionPolicyModel", "ExperimentFixedSelectionPolicyModel", "ExperimentSampleSelectionPolicyModel":
		raw = `{"binding_descriptor_refs":[]}`
	case "ExperimentEpisodeControlModel":
		raw = `{"termination_condition_refs":[]}`
	case "ExperimentEvidenceRecordModel":
		raw = `{"provenance_refs":[]}`
	case termExperimentEvidenceRequirementRelationModel:
		raw = `{"provenance_refs":[],"refinement_dimensions":[]}`
	case "ExperimentExecutionAccountingModel":
		raw = `{"participant_configurations":[]}`
	case "ExperimentFactorLevelEffectsModel":
		raw = `{"bindings":[],"selections":[]}`
	case "ExperimentRunAllocationPlanModel":
		raw = `{"blocking_factors":[]}`
	case modelExperimentRun:
		raw = `{"augmentation_disclosures":[],"derived_from_refs":[],"deviations":[],"evidence_artifacts":[],"evidence_requirement_relations":[],"generated_refs":[],"materialization_attestations":[],"parameter_set":[],"realized_bindings":[],"realized_form_disclosures":[],"realized_selections":[],"result_summaries":{},"stochastic_controls":[],"stochastic_draws":[],"used_refs":[],"validation_basis_disclosures":[]}`
	case modelExperimentRunPlan:
		raw = `{"evidence_requirement_relations":[],"red_variant_selections":{},"selection_policies":{},"stochastic_controls":[]}`
	case "ExperimentRunTraceabilityModel":
		raw = `{"claim_refs":[],"derived_measure_refs":[],"notes":[]}`
	case modelExperimentSpec:
		raw = `{"artifact_refs":[],"capture_spec_refs":[],"factors":{},"validity_notes":[]}`
	case "ExperimentSplitAndLeakageControlsModel":
		raw = `{"grouping_constraints":[],"leakage_checks":[],"unresolved_risks":[]}`
	case "ExperimentStudyFactorModel":
		raw = `{"levels":[]}`
	case modelExperimentStudy:
		raw = `{"behavioral_claims":[],"evidence_requirement_relations":[],"export_artifacts":[],"factors":{},"report_artifacts":[],"research_questions":[],"validation_basis_disclosures":[],"validity_notes":[]}`
	case "ExperimentTaskModel":
		raw = `{"evidence_requirement_relations":[],"non_use":[],"validation_basis_disclosures":[]}`
	case "ParticipantExposurePolicyModel":
		raw = `{"constraints":{},"disclosed_refs":[],"tool_affordance_refs":[],"visibility_scope_refs":[],"withheld_refs":[]}`
	case "ParticipantImplementationProvenanceModel":
		raw = `{"metadata":{}}`
	case "RealizedTimeModelProvenanceModel":
		raw = `{"deviations":[],"timing_limits":[]}`
	case "SchedulerIsolationProofModel":
		raw = `{"dimensions":[]}`
	case "TimeApparatusBindingModel":
		raw = `{"limitations":[]}`
	case "TimeDomainMappingDeclarationModel":
		raw = `{"scale":{"denominator":1,"numerator":1}}`
	case "TimeModelDeclarationModel":
		raw = `{"mappings":{},"progression_policies":{},"temporal_constraints":{}}`
	case "TimeProgressionPolicyDeclarationModel":
		raw = `{"pacing_ratio":{"denominator":1,"numerator":1}}`
	case "TrialCleanupReceiptModel":
		raw = `{"obligation_results":{}}`
	case "TrialExecutionAttemptReferenceModel":
		raw = `{"operation_refs":[]}`
	case "ValidationBasisDisclosureModel":
		raw = `{"diagnostic_refs":[],"evidence_refs":[],"limitations":[],"producer_refs":[]}`
	case "ValidationGateResultModel":
		raw = `{"diagnostic_refs":[],"evidence_refs":[]}`
	default:
		return manifestFactoryValues(model)
	}
	var defaults map[string]any
	if err := decodeExact([]byte(raw), &defaults); err != nil {
		panic("invalid packaged experiment defaults")
	}
	return defaults
}

func experimentRootModel(id string) string {
	switch id {
	case "backend-manifest-v2":
		return termBackendManifestV2Model
	case "processor-manifest-v2":
		return termProcessorManifestV2Model
	case "participant-implementation-manifest-v1":
		return termParticipantImplementationManifestModel

	case "admitted-trial-plan-v1":
		return modelAdmittedTrialPlan
	case "experiment-apparatus-context-v1":
		return "ExperimentApparatusContextModel"
	case "experiment-authoring-input-v1":
		return modelExperimentSpec
	case "experiment-binding-descriptors-v1":
		return "ExperimentBindingDescriptorSetModel"
	case contractExperimentCapture:
		return "ExperimentCaptureSpecModel"
	case "experiment-derived-measure-v1":
		return "ExperimentDerivedMeasureModel"
	case "experiment-evidence-record-v1":
		return "ExperimentEvidenceRecordModel"
	case termExperimentRunV1:
		return modelExperimentRun
	case contractExperimentStudy:
		return modelExperimentStudy
	case "experiment-task-v1":
		return "ExperimentTaskModel"
	case termParticipantConfigurationResultV1:
		return "ParticipantConfigurationResultModel"
	case "trial-cleanup-plan-v1":
		return "TrialCleanupPlanModel"
	case termTrialCleanupReceiptV1:
		return "TrialCleanupReceiptModel"
	}
	return ""
}

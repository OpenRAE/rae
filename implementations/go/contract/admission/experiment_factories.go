package admission

var experimentFactoryJSON = map[string]string{ //nolint:gochecknoglobals // Fixed constructor data; decoded values are never retained.
	modelTrialApparatus:                            `{"capability_refs":[],"participant_manifest_refs":[]}`,
	modelTrialMixedApparatus:                       `{"participant_manifest_refs":[]}`,
	modelAdmittedTrialEntry:                        `{"bindings":[],"participant_configurations":[],"selections":[],"stochastic_draws":[]}`,
	"AdmittedTrialPlanAdmissionModel":              `{"diagnostics":[],"limitations":[]}`,
	modelTrialInputRefs:                            `{"capture_spec_refs":[],"mixed_composition_profile_refs":[]}`,
	modelAdmittedTrialPlan:                         `{"stochastic_controls":{}}`,
	"BehavioralClaimBindingModel":                  defaultEvidenceReferencesJSON,
	"ExperimentRealizedFormDisclosureModel":        defaultEvidenceReferencesJSON,
	"ExperimentResultSummaryModel":                 defaultEvidenceReferencesJSON,
	"CleanStateRequirementModel":                   `{"verification_probe_refs":[]}`,
	"CleanupObligationModel":                       `{"compensation_refs":[],"depends_on":[],"verification_probe_refs":[]}`,
	termCleanupObligationResultModel:               `{"evidence_refs":[],"residual_state_refs":[]}`,
	"DifficultyDecisionRecordModel":                `{"affected_refs":[],"observation_refs":[]}`,
	"DifficultyInterventionRecordModel":            `{"evidence_refs":[],"occurrence_refs":[]}`,
	"DifficultyPolicyModel":                        `{"actions":{},"observation_sources":{},"threshold_rules":{}}`,
	"DifficultyRunProvenanceModel":                 `{"decisions":[],"interventions":[]}`,
	"DifficultyVariantModel":                       `{"action_refs":[],"scaffold_refs":[],"selection_policy_refs":[]}`,
	"ExecutionRetryPolicyModel":                    `{"compensation_refs":[],"reset_obligation_refs":[]}`,
	"ExperimentApparatusComponentModel":            `{"compatibility_refs":[],"limitations":[]}`,
	"ExperimentApparatusConstraintModel":           `{"allowed_backend_refs":[],"allowed_processor_refs":[],"notes":[],"required_capabilities":[],"required_manifest_refs":[]}`,
	termExperimentArtifactRefModel:                 `{"satisfies_refs":[]}`,
	"ExperimentAttemptAccountingModel":             `{"evidence_record_refs":[],"evidence_records":[],"operation_refs":[]}`,
	"ExperimentAugmentationDisclosureModel":        `{"affected_refs":[],"evidence_refs":[],"markings":[],"notes":[]}`,
	"ExperimentCaptureRequirementModel":            `{"notes":[],"required_artifact_roles":[]}`,
	"ExperimentCaptureSpecModel":                   `{"artifact_refs":[],"validity_notes":[]}`,
	termExperimentConditionAssignmentModel:         `{"required_bindings":[],"required_parameters":[],"required_refs":[],"required_selections":[]}`,
	"ExperimentDerivedMeasureMethodModel":          `{"parameters":[]}`,
	"ExperimentRedVariantSelectionModel":           `{"parameters":[]}`,
	"ExperimentDerivedMeasureModel":                `{"limitations":[],"provenance_refs":[]}`,
	"ExperimentEnumerateSelectionPolicyModel":      defaultBindingDescriptorRefsJSON,
	"ExperimentFixedSelectionPolicyModel":          defaultBindingDescriptorRefsJSON,
	"ExperimentSampleSelectionPolicyModel":         defaultBindingDescriptorRefsJSON,
	"ExperimentEpisodeControlModel":                `{"termination_condition_refs":[]}`,
	"ExperimentEvidenceRecordModel":                `{"provenance_refs":[]}`,
	termExperimentEvidenceRequirementRelationModel: `{"provenance_refs":[],"refinement_dimensions":[]}`,
	"ExperimentExecutionAccountingModel":           `{"participant_configurations":[]}`,
	"ExperimentFactorLevelEffectsModel":            `{"bindings":[],"selections":[]}`,
	"ExperimentRunAllocationPlanModel":             `{"blocking_factors":[]}`,
	modelExperimentRun:                             `{"augmentation_disclosures":[],"derived_from_refs":[],"deviations":[],"evidence_artifacts":[],"evidence_requirement_relations":[],"generated_refs":[],"materialization_attestations":[],"parameter_set":[],"realized_bindings":[],"realized_form_disclosures":[],"realized_selections":[],"result_summaries":{},"stochastic_controls":[],"stochastic_draws":[],"used_refs":[],"validation_basis_disclosures":[]}`,
	modelExperimentRunPlan:                         `{"evidence_requirement_relations":[],"red_variant_selections":{},"selection_policies":{},"stochastic_controls":[]}`,
	"ExperimentRunTraceabilityModel":               `{"claim_refs":[],"derived_measure_refs":[],"notes":[]}`,
	modelExperimentSpec:                            `{"artifact_refs":[],"capture_spec_refs":[],"factors":{},"validity_notes":[]}`,
	"ExperimentSplitAndLeakageControlsModel":       `{"grouping_constraints":[],"leakage_checks":[],"unresolved_risks":[]}`,
	"ExperimentStudyFactorModel":                   `{"levels":[]}`,
	modelExperimentStudy:                           `{"behavioral_claims":[],"evidence_requirement_relations":[],"export_artifacts":[],"factors":{},"report_artifacts":[],"research_questions":[],"validation_basis_disclosures":[],"validity_notes":[]}`,
	"ExperimentTaskModel":                          `{"evidence_requirement_relations":[],"non_use":[],"validation_basis_disclosures":[]}`,
	"ParticipantExposurePolicyModel":               `{"constraints":{},"disclosed_refs":[],"tool_affordance_refs":[],"visibility_scope_refs":[],"withheld_refs":[]}`,
	"ParticipantImplementationProvenanceModel":     `{"metadata":{}}`,
	"RealizedTimeModelProvenanceModel":             `{"deviations":[],"timing_limits":[]}`,
	"SchedulerIsolationProofModel":                 `{"dimensions":[]}`,
	"TimeApparatusBindingModel":                    `{"limitations":[]}`,
	"TimeDomainMappingDeclarationModel":            `{"scale":{"denominator":1,"numerator":1}}`,
	"TimeModelDeclarationModel":                    `{"mappings":{},"progression_policies":{},"temporal_constraints":{}}`,
	"TimeProgressionPolicyDeclarationModel":        `{"pacing_ratio":{"denominator":1,"numerator":1}}`,
	"TrialCleanupReceiptModel":                     `{"obligation_results":{}}`,
	"TrialExecutionAttemptReferenceModel":          `{"operation_refs":[]}`,
	"ValidationBasisDisclosureModel":               `{"diagnostic_refs":[],"evidence_refs":[],"limitations":[],"producer_refs":[]}`,
	"ValidationGateResultModel":                    `{"diagnostic_refs":[],"evidence_refs":[]}`,
}

// experimentFactoryValues supplies fresh native constructor defaults.
// Published schema instances, rather than caller names, select each model.
func experimentFactoryValues(model string) map[string]any {
	raw, known := experimentFactoryJSON[model]
	if !known {
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

const (
	defaultEvidenceReferencesJSON    = `{"evidence_refs":[]}`
	defaultBindingDescriptorRefsJSON = `{"binding_descriptor_refs":[]}`
)

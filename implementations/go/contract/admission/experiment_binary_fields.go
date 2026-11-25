package admission

import "strings"

// Fixed paths belong to the pinned model graph; every lookup returns a fresh slice.
var experimentBinaryPaths = map[string]string{ //nolint:gochecknoglobals // Immutable source paths contain no caller data.
	"ApparatusBindingTargetModel":                  "/component_name /component_version /manifest_version /target_id",
	"BindingOwnerModel":                            "/contract_id /contract_version /validator_id /validator_version",
	"DifficultyActionModel":                        "/action_id /carrier_ref /target_variant_id",
	"DifficultyAffectedReferenceModel":             "/ref_id",
	"DifficultyDimensionModel":                     "/dimension_id /ordered_variant_ids/* /ordering_rationale",
	"DifficultyObservationSourceModel":             "/source_id",
	modelDifficultyPolicy:                          "/baseline_variant_id /guardrails/* /policy_digest /policy_id /policy_version /validity_effect",
	"DifficultyPolicyRegistryModel":                "/default_policy_id",
	"DifficultySourceDefinitionReferenceModel":     binaryReferencePaths,
	"DifficultyThresholdRuleModel":                 "/action_id /observation_source_id /rule_id",
	"DifficultyVariantModel":                       "/action_refs/* /description /scaffold_refs/* /selection_policy_refs/* /variant_id",
	"ExperimentAllocationPolicyModel":              "/policy_id /stochastic_control_ref",
	"ExperimentApparatusConstraintModel":           "/notes/* /required_capabilities/*",
	termExperimentArtifactRefModel:                 "/artifact_id /created_at /description /media_type /source /uri",
	"ExperimentBackendReferenceModel":              binaryReferencePaths,
	"ExperimentBindingDescriptorModel":             "/binding_id /source_condition_id /source_factor_id /source_factor_level_id",
	"ExperimentCaptureSpecReferenceModel":          binaryReferencePaths,
	"ExperimentChecksumModel":                      "/value",
	"ExperimentClockContextModel":                  "/authority /clock_id /synchronization",
	termExperimentConditionAssignmentModel:         "/condition_id /description /difficulty_policy_id /factor_levels/*",
	"ExperimentConditionAssignmentParameterModel":  "/name /value",
	"ExperimentConditionAssignmentReferenceModel":  binaryReferencePaths,
	"ExperimentEnumerateSelectionPolicyModel":      "/binding_descriptor_refs/* /point_ref /policy_id",
	"ExperimentEpisodeControlModel":                "/description /termination_condition_refs/* /termination_rule",
	termExperimentEvidenceRequirementRelationModel: "/base_requirement_address /capture_requirement_ref /rationale /relation_id /relation_version",
	"ExperimentEvidenceSatisfactionReferenceModel": binaryReferencePaths,
	"ExperimentFactorLevelSelectionModel":          "/scenario_family_digest",
	"ExperimentFactorialDesignModel":               "/factor_ids/*",
	"ExperimentFactorialTreatmentDesignModel":      "/factor_ids/*",
	"ExperimentFixedSelectionPolicyModel":          "/binding_descriptor_refs/* /point_ref /policy_id",
	"ExperimentManifestReferenceModel":             binaryReferencePaths,
	"ExperimentParameterModel":                     "/name /value",
	"ExperimentProcessorReferenceModel":            binaryReferencePaths,
	"ExperimentProductSelectionPolicyModel":        "/policy_id /policy_refs/*",
	"ExperimentRedVariantSelectionModel":           "/agent_ref /description /variant_id",
	"ExperimentReferenceModel":                     binaryReferencePaths,
	"ExperimentRunAllocationPlanModel":             "/allocation_method /allocation_unit /blocking_factors/* /compared_conditions/* /randomization_unit /replication_policy /stopping_rule",
	"ExperimentSampleSelectionPolicyModel":         "/binding_descriptor_refs/* /logical_coordinate_profile /point_ref /policy_id /stochastic_control_ref",
	"ExperimentScenarioReferenceModel":             binaryReferencePaths,
	"ExperimentScenarioSelectionDescriptorModel":   "/scenario_family_digest /selection_id /source_condition_id /source_factor_id /source_factor_level_id",
	"ExperimentScenarioSnapshotReferenceModel":     binaryReferencePaths,
	"ExperimentSelectionMemberOutcomeModel":        "/member_id",
	"ExperimentSelectionOrderOutcomeModel":         "/member_ids/*",
	"ExperimentSelectionReferenceOutcomeModel":     "/reference_id",
	"ExperimentSelectionStratumModel":              "/condition_id /factor_id /factor_level_id /outcome_ref /stratum_id",
	"ExperimentSelectionSubsetOutcomeModel":        "/member_ids/*",
	"ExperimentSpecModel":                          "/description /spec_id /spec_version /title",
	"ExperimentStochasticControlModel":             "/control_id /description /value",
	"ExperimentStratifiedSelectionPolicyModel":     "/point_ref /policy_id",
	"ExperimentStudyFactorModel":                   "/levels/* /name",
	"ExperimentTaskReferenceModel":                 binaryReferencePaths,
	"ExperimentValidityNoteModel":                  "/mitigation /note",
	"GovernedEntropyRefModel":                      "/reference_id /reference_version",
	"ObservationDemandDocument":                    "/document_id",
	"ObservationDemandRule":                        "/authority_ref /integrity /redaction /rule_id /scope",
	"ObservationSelector":                          "/coverage_profile /semantic_scope",
	"ParticipantImplementationBindingTargetModel":  "/implementation_name /implementation_version /manifest_version /participant_address /target_id",
	"PublicSeedModel":                              "/value",
	"RandomStreamControlBindingModel":              "/namespace",
	"RandomStreamProfileReferenceModel":            binaryReferencePaths,
	"ScenarioBindingTargetModel":                   "/scenario_family_id /target_id /variation_point_id",
	"SecretReferenceBindingValueModel":             "/reference_id",
}

// experimentBinaryFields records non-strict text leaves of the pinned Python
// authoring model graph. Literal tags, strict strings and mapping keys do not coerce bytes.
func experimentBinaryFields(model string) []string {
	return strings.Fields(experimentBinaryPaths[model])
}

const binaryReferencePaths = termRefDigestPath + " " + termRefIDPath + " " + termRefPathPath + " " + termRefVersionPath

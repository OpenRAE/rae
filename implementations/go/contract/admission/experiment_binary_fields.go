package admission

// experimentBinaryFields records non-strict text leaves of the pinned Python
// authoring model graph. Literal tags, strict strings and mapping keys do not coerce bytes.
func experimentBinaryFields(model string) []string {
	switch model {
	case "ApparatusBindingTargetModel":
		return []string{"/component_name", "/component_version", "/manifest_version", termTargetIDPath}
	case "BindingOwnerModel":
		return []string{"/contract_id", "/contract_version", "/validator_id", "/validator_version"}
	case "DifficultyActionModel":
		return []string{"/action_id", "/carrier_ref", "/target_variant_id"}
	case "DifficultyAffectedReferenceModel":
		return []string{termRefIDPath}
	case "DifficultyDimensionModel":
		return []string{"/dimension_id", "/ordered_variant_ids/*", "/ordering_rationale"}
	case "DifficultyObservationSourceModel":
		return []string{"/source_id"}
	case "DifficultyPolicyModel":
		return []string{"/baseline_variant_id", "/guardrails/*", "/policy_digest", termPolicyIDPath, "/policy_version", "/validity_effect"}
	case "DifficultyPolicyRegistryModel":
		return []string{"/default_policy_id"}
	case "DifficultySourceDefinitionReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "DifficultyThresholdRuleModel":
		return []string{"/action_id", "/observation_source_id", "/rule_id"}
	case "DifficultyVariantModel":
		return []string{"/action_refs/*", termDescriptionPath, "/scaffold_refs/*", "/selection_policy_refs/*", "/variant_id"}
	case "ExperimentAllocationPolicyModel":
		return []string{termPolicyIDPath, "/stochastic_control_ref"}
	case "ExperimentApparatusConstraintModel":
		return []string{"/notes/*", "/required_capabilities/*"}
	case termExperimentArtifactRefModel:
		return []string{"/artifact_id", "/created_at", termDescriptionPath, "/media_type", "/source", "/uri"}
	case "ExperimentBackendReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentBindingDescriptorModel":
		return []string{"/binding_id", "/source_condition_id", "/source_factor_id", "/source_factor_level_id"}
	case "ExperimentCaptureSpecReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentChecksumModel":
		return []string{termValuePath}
	case "ExperimentClockContextModel":
		return []string{"/authority", "/clock_id", "/synchronization"}
	case termExperimentConditionAssignmentModel:
		return []string{"/condition_id", termDescriptionPath, "/difficulty_policy_id", "/factor_levels/*"}
	case "ExperimentConditionAssignmentParameterModel":
		return []string{termNamePath, termValuePath}
	case "ExperimentConditionAssignmentReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentEnumerateSelectionPolicyModel":
		return []string{termBindingDescriptorRefsPath, termPointRefPath, termPolicyIDPath}
	case "ExperimentEpisodeControlModel":
		return []string{termDescriptionPath, "/termination_condition_refs/*", "/termination_rule"}
	case termExperimentEvidenceRequirementRelationModel:
		return []string{"/base_requirement_address", "/capture_requirement_ref", "/rationale", "/relation_id", "/relation_version"}
	case "ExperimentEvidenceSatisfactionReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentFactorLevelSelectionModel":
		return []string{"/scenario_family_digest"}
	case "ExperimentFactorialDesignModel":
		return []string{"/factor_ids/*"}
	case "ExperimentFactorialTreatmentDesignModel":
		return []string{"/factor_ids/*"}
	case "ExperimentFixedSelectionPolicyModel":
		return []string{termBindingDescriptorRefsPath, termPointRefPath, termPolicyIDPath}
	case "ExperimentManifestReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentParameterModel":
		return []string{termNamePath, termValuePath}
	case "ExperimentProcessorReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentProductSelectionPolicyModel":
		return []string{termPolicyIDPath, "/policy_refs/*"}
	case "ExperimentRedVariantSelectionModel":
		return []string{"/agent_ref", termDescriptionPath, "/variant_id"}
	case "ExperimentReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentRunAllocationPlanModel":
		return []string{"/allocation_method", "/allocation_unit", "/blocking_factors/*", "/compared_conditions/*", "/randomization_unit", "/replication_policy", "/stopping_rule"}
	case "ExperimentSampleSelectionPolicyModel":
		return []string{termBindingDescriptorRefsPath, "/logical_coordinate_profile", termPointRefPath, termPolicyIDPath, "/stochastic_control_ref"}
	case "ExperimentScenarioReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentScenarioSelectionDescriptorModel":
		return []string{"/scenario_family_digest", "/selection_id", "/source_condition_id", "/source_factor_id", "/source_factor_level_id"}
	case "ExperimentScenarioSnapshotReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentSelectionMemberOutcomeModel":
		return []string{"/member_id"}
	case "ExperimentSelectionOrderOutcomeModel":
		return []string{"/member_ids/*"}
	case "ExperimentSelectionReferenceOutcomeModel":
		return []string{termReferenceIDPath}
	case "ExperimentSelectionStratumModel":
		return []string{"/condition_id", "/factor_id", "/factor_level_id", "/outcome_ref", "/stratum_id"}
	case "ExperimentSelectionSubsetOutcomeModel":
		return []string{"/member_ids/*"}
	case "ExperimentSpecModel":
		return []string{termDescriptionPath, "/spec_id", "/spec_version", "/title"}
	case "ExperimentStochasticControlModel":
		return []string{"/control_id", termDescriptionPath, termValuePath}
	case "ExperimentStratifiedSelectionPolicyModel":
		return []string{termPointRefPath, termPolicyIDPath}
	case "ExperimentStudyFactorModel":
		return []string{"/levels/*", termNamePath}
	case "ExperimentTaskReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ExperimentValidityNoteModel":
		return []string{"/mitigation", "/note"}
	case "GovernedEntropyRefModel":
		return []string{termReferenceIDPath, "/reference_version"}
	case "ObservationDemandDocument":
		return []string{"/document_id"}
	case "ObservationDemandRule":
		return []string{"/authority_ref", "/integrity", "/redaction", "/rule_id", "/scope"}
	case "ObservationSelector":
		return []string{"/coverage_profile", "/semantic_scope"}
	case "ParticipantImplementationBindingTargetModel":
		return []string{"/implementation_name", "/implementation_version", "/manifest_version", "/participant_address", termTargetIDPath}
	case "PublicSeedModel":
		return []string{termValuePath}
	case "RandomStreamControlBindingModel":
		return []string{"/namespace"}
	case "RandomStreamProfileReferenceModel":
		return []string{termRefDigestPath, termRefIDPath, termRefPathPath, termRefVersionPath}
	case "ScenarioBindingTargetModel":
		return []string{"/scenario_family_id", termTargetIDPath, "/variation_point_id"}
	case "SecretReferenceBindingValueModel":
		return []string{termReferenceIDPath}
	default:
		return nil
	}
}

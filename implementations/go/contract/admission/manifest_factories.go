package admission

// manifestFactoryValues supplies fresh constructor collections for published models.
func manifestFactoryValues(model string) map[string]any {
	var raw string
	switch model {
	case termBackendManifestV2Model, termParticipantImplementationManifestModel, termProcessorManifestV2Model:
		raw = `{"constraints":{}}`
	case termConfigurationTargetDeclarationModel:
		raw = `{"aliases":[]}`
	case "EvaluatorCapabilitiesModel":
		raw = `{"constraints":{},"supported_evidence_channels":[],"supported_predicate_families":[],"supported_quantifiers":[],"supported_time_domains":[],"supported_truth_outcomes":[]}`
	case "ObservationCapabilitiesModel":
		raw = `{"capture_offers":[],"constraints":{}}`
	case "ObservationCaptureOfferModel":
		raw = `{"channel_kinds":[],"channel_refs":[],"retention_policy_refs":[],"scope_refs":[],"source_refs":[]}`
	case "OrchestratorCapabilitiesModel":
		raw = `{"constraints":{},"supported_workflow_features":[],"supported_workflow_state_predicates":[]}`
	case "ParticipantFeatureSupportModel":
		raw = `{"constraint_refs":[],"disclosure_refs":[],"evidence_refs":[],"limitation_refs":[]}`
	case "ParticipantImplementationCompatibilityModel":
		raw = `{"backends":[],"participant_runtimes":[],"processors":[]}`
	case "ParticipantResourceBudgetCapabilitiesModel":
		raw = `{"cross_range_pool_refs":[]}`
	case termParticipantRuntimeCapabilitiesModel:
		raw = `{"constraints":{},"execution_bindings":[],"feature_support":[],"supported_autonomous_action_contracts":[],"supported_autonomous_activity_features":[],"supported_autonomous_observation_boundaries":[],"supported_autonomous_policy_profiles":[],"supported_autonomous_random_stream_profiles":[],"supported_autonomous_selection_strategies":[],"supported_autonomous_target_addresses":[],"supported_execution_control_actions":[]}`
	case "ProvisionerCapabilitiesModel":
		raw = `{"constraints":{},"operating_systems":[],"supported_account_features":[],"supported_content_types":[],"supported_domain_profiles":[],"supported_generated_artifact_delivery_modes":[],"supported_generated_artifact_kinds":[],"supported_node_architectures":[],"supported_regeneration_scopes":[],"supported_service_materialization_profiles":[]}`
	case "RealizationSupportDeclarationModel":
		raw = `{"artifact_mechanisms":[],"constraints":{},"observation_capabilities":{},"process_resource_limits":[],"supported_constraint_kinds":[],"supported_exact_requirement_kinds":[]}`
	case "TimeCapabilitiesModel":
		raw = `{"constraints":{},"supported_constraint_kinds":[],"supported_mapping_kinds":[]}`
	default:
		return nil
	}
	var values map[string]any
	if decodeExact([]byte(raw), &values) != nil {
		panic("invalid packaged manifest defaults")
	}
	return values
}

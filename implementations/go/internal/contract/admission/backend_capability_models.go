package admission

import "strings"

func (e *Validator) vocabularyFields(v any, prefix string, fields ...string) error {
	for _, field := range fields {
		var values []any
		for _, value := range array(at(v, field)) {
			if _, stringValue := value.(string); stringValue {
				values = append(values, value)
			}
		}
		if !e.vocabularyScope(prefix+field, values) {
			return invalid()
		}
	}
	return nil
}

func (e *Validator) provisionerCapability(v any) error {
	if err := e.vocabularyFields(v, "capabilities.provisioner.", "supported_node_types", "supported_os_families", "supported_node_architectures", "supported_content_types", "supported_account_features", "supported_domain_profiles", "supported_service_materialization_profiles"); err != nil {
		return err
	}
	rows := array(at(v, "operating_systems"))
	if len(rowTupleSet(rows, "family", "distribution")) != len(rows) || !subset(rowIDs(rows, "family"), set(at(v, "supported_os_families"))) {
		return invalid()
	}
	if boolean(at(v, "supports_accounts")) != (len(array(at(v, "supported_account_features"))) > 0) {
		return invalid()
	}
	return provisionerArtifacts(v)
}

func provisionerArtifacts(v any) error {
	if !fieldsUnique(v, "supported_generated_artifact_kinds", "supported_generated_artifact_delivery_modes", "supported_regeneration_scopes") {
		return invalid()
	}
	generated := boolean(at(v, "supports_generated_artifacts"))
	if generated != (len(array(at(v, "supported_generated_artifact_kinds"))) > 0) || !generated && len(array(at(v, "supported_generated_artifact_delivery_modes"))) > 0 {
		return invalid()
	}
	return require(set(at(v, "supported_generated_artifact_kinds"))["random_value"] == (len(array(at(v, "supported_regeneration_scopes"))) > 0))
}

func (e *Validator) operatingSystemCapability(v any) error {
	if !e.vocabularyScope("capabilities.provisioner.supported_os_families", []any{at(v, "family")}) || !e.vocabularyScope("capabilities.provisioner.operating_systems.distribution", []any{at(v, "distribution")}) || !fieldsUnique(v, "versions") {
		return invalid()
	}
	expected := coreDistributionFamily(stringAt(v, "distribution"))
	return require(expected == "" || expected == stringAt(v, "family"))
}

func (e *Validator) orchestratorCapability(v any) error {
	if err := e.vocabularyFields(v, "capabilities.orchestrator.", "supported_sections"); err != nil {
		return err
	}
	workflows := boolean(at(v, "supports_workflows"))
	if workflows != set(at(v, "supported_sections"))["workflows"] || workflows != (len(array(at(v, "supported_workflow_features"))) > 0) {
		return invalid()
	}
	return require(workflows || len(array(at(v, "supported_workflow_state_predicates"))) == 0)
}

func (e *Validator) evaluatorCapability(v any) error {
	if err := e.vocabularyFields(v, "capabilities.evaluator.", "supported_sections"); err != nil {
		return err
	}
	if !boolean(defaultMember(v, "supports_scoring", true)) && !boolean(defaultMember(v, "supports_objectives", true)) {
		return invalid()
	}
	fields := []string{"supported_predicate_families", "supported_quantifiers", "supported_truth_outcomes", "supported_evidence_channels", "supported_time_domains"}
	if !fieldsUnique(v, fields...) {
		return invalid()
	}
	sections := set(at(v, "supported_sections"))
	if !sections["propositions"] && !sections["assertions"] {
		return nil
	}
	if !sections["propositions"] || !sections["assertions"] || !boolean(at(v, "preserves_binding_provenance")) || !equalSet(set(at(v, "supported_truth_outcomes")), set(jsonStrings([]string{"true", "false", statusUnknown, statusUnsupported}))) {
		return invalid()
	}
	for _, field := range fields {
		if len(array(at(v, field))) == 0 {
			return invalid()
		}
	}
	return nil
}

func (e *Validator) observationCapability(v any) error {
	if err := e.vocabularyFields(v, "capabilities.observation.", "supported_capture_kinds", "supported_channel_kinds", "supported_sealing_modes"); err != nil {
		return err
	}
	if !fieldsUnique(v, "supported_capture_kinds", "supported_channel_kinds", "supported_evidence_contracts", "supported_media_types", "supported_sealing_modes") || !declaredManifestContracts(at(v, "supported_evidence_contracts"), kindBackend) {
		return invalid()
	}
	for _, id := range stringsOf(at(v, "supported_evidence_contracts")) {
		if !strings.HasPrefix(id, "experiment-") {
			return invalid()
		}
	}
	offers := array(at(v, "capture_offers"))
	if len(rowSet(offers, "offer_id")) != len(offers) {
		return invalid()
	}
	for _, offer := range offers {
		if !set(at(v, "supported_capture_kinds"))[stringAt(offer, "capture_kind")] || !subset(stringsOf(at(offer, "channel_kinds")), set(at(v, "supported_channel_kinds"))) || !subset(stringsOf(at(offer, "media_types")), set(at(v, "supported_media_types"))) {
			return invalid()
		}
	}
	return nil
}

func cleanupCapability(v any) error {
	return require(fieldsUnique(v, "supported_contract_versions", "supported_action_kinds", "supported_verification_methods") && equalSet(set(at(v, "supported_contract_versions")), set(jsonStrings(backendFamilyContracts(termCleanup)))) && (!boolean(at(v, "supports_reusable_state")) || boolean(at(v, "supports_residual_state_disclosure"))))
}

func timeCapability(v any) error {
	if !fieldsUnique(v, "supported_contract_versions") || !equalSet(set(at(v, "supported_contract_versions")), set(jsonStrings(backendFamilyContracts("time")))) {
		return invalid()
	}
	for _, field := range []string{"supported_domain_kinds", "supported_authority_kinds", "supported_advancement_modes", "supported_synchronization_modes", "supported_mapping_kinds", "supported_constraint_kinds", "supported_reset_behaviors", "supported_replay_behaviors"} {
		if !fieldsUnique(v, field) || !subset(stringsOf(at(v, field)), set(jsonStrings(timeCapabilityTerms(field)))) {
			return invalid()
		}
	}
	return require(len(array(at(v, "supported_mapping_kinds"))) == 0 || boolean(at(v, "supports_exact_rational_mappings")))
}

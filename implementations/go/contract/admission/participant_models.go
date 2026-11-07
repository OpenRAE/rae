package admission

func participantContractVersions(values any) bool {
	return declaredManifestContracts(values, termParticipant)
}

// vocabularyScope admits each value through the vocabulary that governs the
// scope. A scope that no vocabulary governs admits only an empty list.
func (e *Validator) vocabularyScope(scope string, values any) bool {
	vocabulary, governed := e.authority.ScopeVocabulary(scope)
	if !governed {
		return len(array(values)) == 0
	}
	for _, value := range stringsOf(values) {
		if !e.authority.Permits(vocabulary.ID, value) {
			return false
		}
	}
	return true
}

func (e *Validator) participantManifest(v any) error {
	if err := manifestConfigurationTargets(v); err != nil {
		return err
	}
	versions := at(v, "supported_contract_versions")
	if !participantContractVersions(versions) || !subset(stringsOf(at(v, "capabilities", "supported_participant_contracts")), set(versions)) {
		return invalid()
	}
	if at(v, "configuration_registry") != nil && (!set(versions)[termExperimentBindingDescriptorsV1] || !set(versions)["participant-configuration-result-v1"]) {
		return invalid()
	}
	bindings := array(at(v, "concept_bindings"))
	if len(rowSet(bindings, "scope")) != len(bindings) {
		return invalid()
	}
	for _, binding := range bindings {
		scope := stringAt(binding, "scope")
		if !participantConceptScope(scope) || !e.knownFamily(stringAt(binding, "family")) || !manifestScopePresent(v, scope) {
			return invalid()
		}
	}
	return require(e.vocabularyScope("implementation_kind", []any{at(v, "implementation_kind")}))
}

func (e *Validator) participantCapabilities(v any) error {
	for _, field := range []string{"supported_participant_contracts", "supported_decision_surface_modes", "tool_affordance_expectations", "exposure_policy_kinds"} {
		if !fieldsUnique(v, field) || !e.vocabularyScope("capabilities."+field, at(v, field)) {
			return invalid()
		}
	}
	return require(participantContractVersions(at(v, "supported_participant_contracts")))
}

func (e *Validator) participantSelection(v any) error {
	return require((at(v, "configuration_ref") == nil) == (at(v, "configuration_digest") == nil) && participantContractVersions(at(v, "participant_contract_versions")) && e.vocabularyScope("capabilities.supported_decision_surface_modes", []any{at(v, "selected_decision_surface_mode")}))
}

func (e *Validator) participantExposure(v any) error {
	fields := []string{"disclosed_refs", "withheld_refs", "tool_affordance_refs", "visibility_scope_refs"}
	count := 0
	for _, field := range fields {
		count += len(array(at(v, field)))
	}
	return require(count > 0 && fieldsUnique(v, fields...) && fieldsUnique(v, "exposure_policy_kinds") && e.vocabularyScope("capabilities.exposure_policy_kinds", at(v, "exposure_policy_kinds")))
}

func participantCompatibility(v any) error {
	return require(fieldsUnique(v, "participant_runtimes", "processors", "backends") && len(array(at(v, "participant_runtimes")))+len(array(at(v, "processors")))+len(array(at(v, "backends"))) > 0)
}

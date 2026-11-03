package admission

import "slices"

func participantContractVersions(values any) bool {
	return declaredManifestContracts(values, "participant")
}

func (e *Validator) vocabularyScope(scope string, values any) bool {
	for id, definition := range e.vocabularies {
		if !set(at(definition, "governed_scopes"))[scope] {
			continue
		}
		for _, value := range stringsOf(values) {
			if !e.vocabularyTerm(id, value) {
				return false
			}
		}
		return true
	}
	return len(array(values)) == 0
}

func (e *Validator) participantManifest(v any) error {
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
		if !slices.Contains([]string{"implementation_kind", "capabilities.supported_participant_contracts", "capabilities.supported_decision_surface_modes", "capabilities.tool_affordance_expectations", "capabilities.exposure_policy_kinds"}, scope) || e.conceptFamilies[stringAt(binding, "family")] == nil || !manifestScopePresent(v, scope) {
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

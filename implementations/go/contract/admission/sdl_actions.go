package admission

func nonblankSDLRefs(v any, fields ...string) bool {
	for _, field := range fields {
		if value := at(v, field); value != nil && !nonblankSDLValues(value) {
			return false
		}
	}
	return true
}

func nonblankSDLValues(value any) bool {
	values, ok := value.([]any)
	if !ok {
		return false
	}
	seen := map[string]bool{}
	for _, raw := range values {
		value, ok := raw.(string)
		if !ok || sdlBlank(value) || seen[value] {
			return false
		}
		seen[value] = true
	}
	return true
}
func sdlActionPrecondition(v any) error {
	return require(nonblankSDLFields(v, "precondition_id", termDescription) && nonblankSDLRefs(v, "support_refs", fieldEvidenceRefs))
}
func sdlActionEffect(v any) error {
	if !nonblankSDLFields(v, "effect_id", termDescription) || !nonblankSDLRefs(v, "target_refs", fieldEvidenceRefs) {
		return invalid()
	}
	if stringAt(v, "effect_class") == "no_effect" || stringAt(v, "effect_class") == "unknown_effect" {
		return nil
	}
	return require(len(array(at(v, "target_refs")))+len(array(at(v, fieldEvidenceRefs))) > 0)
}
func sdlActionContract(v any) error {
	if !nonblankSDLFields(v, "semantic_version", "procedure_basis", "realization_profile", "fidelity_claim") || !nonblankSDLRefs(v, "state_transition_effects", "observation_expectations", "evidence_expectations", "failure_classes") {
		return invalid()
	}
	for field, key := range map[string]string{"preconditions": "precondition_id", "effects": "effect_id"} {
		rows := array(at(v, field))
		if len(rows) == 0 || len(rowTupleSet(rows, key)) != len(rows) {
			return invalid()
		}
	}
	if len(array(at(v, "failure_classes"))) == 0 {
		return invalid()
	}
	mappings := array(at(v, "backend_failure_mappings"))
	if len(rowTupleSet(mappings, "backend_error_code")) != len(mappings) {
		return invalid()
	}
	failures := set(at(v, "failure_classes"))
	for _, mapping := range mappings {
		if !failures[stringAt(mapping, "failure_class")] {
			return invalid()
		}
	}
	return sdlActionTemporalPayload(v)
}
func sdlActionTemporalPayload(v any) error {
	contracts, disclosures := array(at(v, "temporal_contracts")), array(at(v, "backend_timing_disclosures"))
	temporalIDs, disclosureIDs := rowSet(contracts, "temporal_id"), rowSet(disclosures, "disclosure_id")
	if len(temporalIDs) != len(contracts) || len(disclosureIDs) != len(disclosures) {
		return invalid()
	}
	if len(contracts) == 0 {
		if len(disclosures) > 0 {
			return invalid()
		}
		for _, precondition := range array(at(v, "preconditions")) {
			if stringAt(precondition, "precondition_class") == "temporal" {
				return invalid()
			}
		}
	}
	return sdlActionTemporalReferences(contracts, disclosures, temporalIDs, disclosureIDs)
}

func sdlActionTemporalReferences(contracts, disclosures []any, temporalIDs, disclosureIDs map[string]bool) error {
	for _, contract := range contracts {
		if !subset(stringsOf(at(contract, "backend_disclosure_refs")), disclosureIDs) {
			return invalid()
		}
	}
	for _, disclosure := range disclosures {
		if !subset(stringsOf(at(disclosure, "affected_temporal_ids")), temporalIDs) {
			return invalid()
		}
	}
	return nil
}

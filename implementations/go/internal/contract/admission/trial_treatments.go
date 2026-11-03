package admission

func entryConfigurations(v any) error {
	configurations := map[string]any{}
	for _, result := range array(at(v, "participant_configurations")) {
		address := stringAt(result, fieldParticipantAddress)
		if configurations[address] != nil {
			return invalid()
		}
		configurations[address] = result
		if !entryManifestAuthority(v, result, at(result, termConfiguration, "implementation_identity", termName), at(result, termConfiguration, "implementation_identity", "version"), at(result, termConfiguration, "manifest_version")) {
			return invalid()
		}
	}
	for _, binding := range array(at(v, termBindings)) {
		if err := entryConfigurationBinding(v, binding, configurations); err != nil {
			return err
		}
	}
	return nil
}

func entryManifestAuthority(entry, result, name, version, manifest any) bool {
	for _, ref := range array(at(entry, termApparatus, "participant_manifest_refs")) {
		if equal(at(ref, fieldParticipantAddress), at(result, fieldParticipantAddress)) && equal(at(ref, "implementation_name"), name) && equal(at(ref, "implementation_version"), version) && equal(at(ref, "manifest_version"), manifest) && equal(at(ref, "manifest_digest"), at(result, "manifest_digest")) {
			return true
		}
	}
	return false
}

func trialTreatments(plan any) error {
	for _, entry := range object(at(plan, "entries")) {
		if err := trialEntryTreatments(plan, entry); err != nil {
			return err
		}
	}
	return nil
}

func trialEntryTreatments(plan, entry any) error {
	bound := map[string]bool{}
	levels := map[string]string{}
	for _, binding := range array(at(entry, termBindings)) {
		if err := trialTreatmentBinding(plan, entry, binding, bound, levels); err != nil {
			return err
		}
	}
	selections := []any{}
	for _, record := range array(at(entry, "selections")) {
		selection := at(record, "treatment")
		if selection == nil {
			if stringAt(record, "origin_policy_id") == termFactorialTreatmentsV1 && stringAt(record, "origin_policy_kind") == termStratified && !bound[stringAt(record, "variation_point_id")] {
				return invalid()
			}
			continue
		}
		if stringAt(plan, "profiles", "treatment_profile") != termFactorialTreatmentsV1 || !equal(at(selection, "source_condition_id"), at(entry, "coordinate", "condition_id")) || !equal(at(selection, "target", "scenario_family_id"), at(plan, "input_refs", "scenario_family_ref", "ref_id")) || !equal(at(selection, "scenario_family_digest"), at(plan, "input_refs", "scenario_family_ref", "ref_digest")) {
			return invalid()
		}
		selections = append(selections, selection)
	}
	return trialTreatmentSelections(entry, selections, levels)
}

func entryConfigurationBinding(v, binding any, configurations map[string]any) error {
	descriptor := at(binding, "descriptor")
	target := at(descriptor, "target")
	if stringAt(target, "plane") != "participant-implementation" {
		return nil
	}
	result := configurations[stringAt(target, fieldParticipantAddress)]
	if result == nil || !entryManifestAuthority(v, result, at(target, "implementation_name"), at(target, "implementation_version"), at(target, "manifest_version")) {
		return invalid()
	}
	found := false
	for _, value := range array(at(result, termConfiguration, "values")) {
		if equal(at(value, "target_id"), at(target, "target_id")) {
			found = referenceJSONEqual(at(value, "value"), at(descriptor, "value")) && equal(at(value, "value_type"), at(descriptor, "value_type")) && equal(at(result, termConfiguration, "owner"), at(descriptor, "owner"))
		}
	}
	if !found {
		return invalid()
	}

	return nil
}

func trialTreatmentSelections(entry any, selections []any, levels map[string]string) error {
	if len(selections) == 0 {
		return nil
	}
	if !unique(rowIDs(selections, "selection_id")) {
		return invalid()
	}
	points := map[string]bool{}
	for _, binding := range array(at(entry, termBindings)) {
		if stringAt(binding, "descriptor", "target", "plane") == kindScenario {
			points[join(stringAt(binding, "descriptor", "target", "scenario_family_id"), stringAt(binding, "descriptor", "target", "variation_point_id"))] = true
		}
	}
	for _, selection := range selections {
		point := join(stringAt(selection, "target", "scenario_family_id"), stringAt(selection, "target", "variation_point_id"))
		if points[point] {
			return invalid()
		}
		points[point] = true
		factor, level := stringAt(selection, "source_factor_id"), stringAt(selection, "source_factor_level_id")
		if previous, exists := levels[factor]; exists && previous != level {
			return invalid()
		}
		levels[factor] = level
	}
	// Source levels on bindings must agree too, even when no selection uses that factor.
	for _, binding := range array(at(entry, termBindings)) {
		descriptor := at(binding, "descriptor")
		if levels[stringAt(descriptor, "source_factor_id")] != stringAt(descriptor, "source_factor_level_id") {
			return invalid()
		}
	}
	return nil
}

func trialTreatmentBinding(plan, entry, binding any, bound map[string]bool, levels map[string]string) error {
	descriptor := at(binding, "descriptor")
	if at(entry, "coordinate", "condition_id") != nil && !equal(at(descriptor, "source_condition_id"), at(entry, "coordinate", "condition_id")) {
		return invalid()
	}
	if stringAt(descriptor, "target", "plane") == kindScenario {
		if !equal(at(descriptor, "target", "scenario_family_id"), at(plan, "input_refs", "scenario_family_ref", "ref_id")) {
			return invalid()
		}
		bound[stringAt(descriptor, "target", "variation_point_id")] = true
	}
	levels[stringAt(descriptor, "source_factor_id")] = stringAt(descriptor, "source_factor_level_id")

	return nil
}

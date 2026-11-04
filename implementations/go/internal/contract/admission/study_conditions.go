package admission

func runCondition(run, assignment any) bool {
	for _, ref := range array(at(assignment, "required_refs")) {
		if !conditionReference(run, ref) {
			return false
		}
	}
	if !conditionParameters(run, assignment) {
		return false
	}
	condition, policy := conditionFixed, any(nil)
	if at(run, "difficulty_provenance") != nil {
		condition = stringAt(run, "difficulty_provenance", termPolicy, "condition")
		policy = at(run, "difficulty_provenance", termPolicy, "policy_id")
	}
	if text(defaultMember(assignment, "difficulty_condition", conditionFixed)) != condition || at(assignment, "difficulty_policy_id") != nil && !equal(at(assignment, "difficulty_policy_id"), policy) {
		return false
	}
	return conditionBindingsAndSelections(run, assignment)
}

func referenceJSONEqual(a, b any) bool {
	if left, ok := a.(map[string]any); ok {
		return referenceObjectEqual(left, b)
	}
	if left, ok := a.([]any); ok {
		right, ok := b.([]any)
		if !ok || len(left) != len(right) {
			return false
		}
		for j, value := range left {
			if !referenceJSONEqual(value, right[j]) {
				return false
			}
		}
		return true
	}
	if a == nil || b == nil {
		return a == nil && b == nil
	}
	return referenceScalarEqual(a, b)
}
func bindingConfiguration(run, binding any) bool {
	target := at(binding, "descriptor", "target")
	if stringAt(target, fieldPlane) != kindParticipantImplementation {
		return true
	}
	for _, selection := range array(at(run, "participant_implementation_provenance", "participant_implementations")) {
		if equal(at(selection, fieldParticipantAddress), at(target, fieldParticipantAddress)) && equal(at(selection, "implementation_identity", termName), at(target, "implementation_name")) && equal(at(selection, "implementation_identity", "version"), at(target, "implementation_version")) && equal(at(selection, "configuration_digest"), at(binding, "configuration_digest")) {
			return true
		}
	}
	return false
}
func conditionReference(run, ref any) bool {
	kind := stringAt(ref, fieldRefKind)
	apparatus := at(run, "apparatus_context")
	switch kind {
	case termEvidence:
		return false // Structural validation cannot mint a content-backed proof.
	case kindProcessor, kindBackend, kindParticipantImplementation:
		return conditionImplementation(run, ref, kind)
	case kindTask:
		return referenceSatisfies(at(run, "task_ref"), ref)
	case kindScenarioSnapshot:
		return referenceSatisfies(at(run, "scenario_snapshot_ref"), ref)
	case kindApparatusContext:
		return referenceSatisfies(map[string]any{fieldRefKind: kindApparatusContext, fieldRefID: at(apparatus, "apparatus_context_id"), fieldRefVersion: at(apparatus, "context_version")}, ref)
	case termManifest:
		return referenceIn(at(apparatus, "selected_manifests"), ref)
	case termProfile, "capability":
		if referenceIn(at(apparatus, "compatibility_declarations"), ref) {
			return true
		}
		for _, component := range object(at(run, "apparatus_context", termComponents)) {
			if referenceIn(at(component, "compatibility_refs"), ref) {
				return true
			}
		}
	case "measurement-channel":
		return referenceIn(at(apparatus, "measurement_channels"), ref)
	default:
		return referenceIn(at(run, "used_refs"), ref) || referenceIn(at(run, "generated_refs"), ref) || referenceIn(at(run, "derived_from_refs"), ref)
	}
	return false
}

func conditionParameters(run, assignment any) bool {
	parameters := append([]any{}, array(at(run, "parameter_set"))...)
	parameters = append(parameters, array(at(run, "apparatus_context", "configuration_parameters"))...)
	for _, required := range array(at(assignment, "required_parameters")) {
		found := false
		for _, candidate := range parameters {
			if matchingFields(candidate, required, termName, "value_kind") && referenceJSONEqual(at(candidate, "value"), at(required, "value")) {
				found = true
			}
		}
		if !found {
			return false
		}
	}
	return true
}

func conditionBindingsAndSelections(run, assignment any) bool {
	for _, required := range array(at(assignment, termRequiredBindings)) {
		found := false
		expected := realizationMeaning(required, "binding_id")
		for _, binding := range array(at(run, "realized_bindings")) {
			if equal(expected, realizationMeaning(at(binding, "descriptor"), "binding_id")) && bindingConfiguration(run, binding) {
				found = true
			}
		}
		if !found {
			return false
		}
	}
	return conditionSelections(run, assignment)
}

func referenceObjectEqual(left map[string]any, b any) bool {
	right, ok := b.(map[string]any)
	if !ok || len(left) != len(right) {
		return false
	}
	for key, value := range left {
		other, present := right[key]
		if !present || !referenceJSONEqual(value, other) {
			return false
		}
	}
	return true
}

func conditionImplementation(run, ref any, kind string) bool {
	switch kind {
	case kindProcessor, kindBackend:
		for _, component := range object(at(run, "apparatus_context", termComponents)) {
			if stringAt(component, "component_kind") == kind && identityMatches(at(component, termIdentity), ref) {
				return true
			}
		}
	case kindParticipantImplementation:
		for _, selection := range array(at(run, "participant_implementation_provenance", "participant_implementations")) {
			if identityMatches(at(selection, "implementation_identity"), ref) {
				return true
			}
		}
	}
	return false
}

func conditionSelections(run, assignment any) bool {
	for _, required := range array(at(assignment, termRequiredSelections)) {
		found := false
		for _, selection := range array(at(run, "realized_selections")) {
			if equal(required, selection) {
				found = true
			}
		}
		if !found {
			return false
		}
	}
	return true
}

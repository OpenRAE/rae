package admission

func (e *Validator) semanticProfile(v any) error {
	for _, phase := range []string{"authoring", "exchange", "processing", "execution"} {
		model := at(v, phase)
		if err := e.semanticProfilePhase(model); err != nil {
			return err
		}
		for _, binding := range array(at(model, "required_bindings")) {
			scope := stringAt(binding, "scope")
			allowed := phase == "processing" && processorConceptScope(scope) || phase == "execution" && (backendConceptScope(scope) || participantConceptScope(scope))
			if !allowed {
				return invalid()
			}
		}
	}
	return nil
}

func (e *Validator) semanticProfilePhase(v any) error {
	if !fieldsUnique(v, "required_contracts", "required_concept_families") {
		return invalid()
	}
	for _, id := range stringsOf(at(v, "required_contracts")) {
		if !e.low.HasContract(id) {
			return invalid()
		}
	}
	families := set(at(v, "required_concept_families"))
	for id := range families {
		if !e.knownFamily(id) {
			return invalid()
		}
	}
	bindings := array(at(v, "required_bindings"))
	assumptions := array(at(v, "behavior_assumptions"))
	if len(rowSet(bindings, "scope")) != len(bindings) || len(rowSet(assumptions, "id")) != len(assumptions) {
		return invalid()
	}
	for _, binding := range bindings {
		if !families[stringAt(binding, "family")] {
			return invalid()
		}
	}
	return nil
}

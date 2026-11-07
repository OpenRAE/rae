package admission

func (e *Validator) satisfiabilityModel(root any) error {
	v, err := e.defaulted("scenario-satisfiability-evidence-v1", root)
	if err != nil {
		return err
	}
	model := at(v, "normalized_model")
	if !equal(at(v, termSource, "byte_digest"), at(model, "source_digest")) || !equal(at(v, "authored_digest"), at(model, "authored_digest")) {
		return invalid()
	}
	for field, digestField := range map[string]string{"normalized_model": "normalized_model_digest", "solver_configuration": "solver_configuration_digest"} {
		actual, err := jsonDigest(at(v, field))
		if err != nil || actual != stringAt(v, digestField) {
			return invalid()
		}
	}
	return satisfiabilityOutcome(v, model)
}

func satisfiabilityOutcome(v, model any) error {
	selected := map[string]string{"satisfiable": "witness", "unsatisfiable": "unsat_core", statusUnsupported: statusUnsupported}[stringAt(v, "outcome")]
	count := 0
	for _, field := range []string{"witness", "unsat_core", statusUnsupported} {
		if at(v, field) != nil {
			count++
		}
	}
	if count != 1 || selected == "" || at(v, selected) == nil {
		return invalid()
	}
	if core := at(v, "unsat_core"); core != nil {
		ids := stringsOf(at(core, "clause_ids"))
		if !sortedUnique(ids) || !subset(ids, rowSet(at(model, "clauses"), "clause_id")) {
			return invalid()
		}
	}
	if unsupported := at(v, statusUnsupported); unsupported != nil {
		ids := stringsOf(at(unsupported, "reason_codes"))
		if !sortedUnique(ids) || !equalSet(set(jsonStrings(ids)), rowSet(at(v, "diagnostics"), "code")) {
			return invalid()
		}
	}
	return nil
}

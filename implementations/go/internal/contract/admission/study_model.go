package admission

func studyFactorDeclarations(v any) error {
	if err := studyDefinition(v); err != nil {
		return err
	}
	factors := object(at(v, "factors"))
	allocation := at(v, "run_allocation")
	for _, id := range stringsOf(at(allocation, "blocking_factors")) {
		factor := factors[id]
		if factor == nil || len(array(at(factor, "levels"))) == 0 {
			return invalid()
		}
		switch stringAt(factor, "factor_kind") {
		case "blocking", "stratification", "apparatus", "control":
		default:
			return invalid()
		}
	}
	for _, assignment := range object(at(allocation, "condition_assignments")) {
		for id, level := range object(at(assignment, "factor_levels")) {
			if factors[id] == nil || !set(at(factors[id], "levels"))[text(level)] {
				return invalid()
			}
		}
	}
	return nil
}

func studyDefinition(v any) error {
	if ref := at(v, "definition_ref"); ref != nil && (stringAt(ref, "ref_kind") != "study" || !equal(at(ref, "ref_id"), at(v, "study_id")) || at(ref, "ref_version") == nil || at(ref, "ref_digest") == nil || at(ref, "ref_path") != nil) {
		return invalid()
	}
	return nil
}

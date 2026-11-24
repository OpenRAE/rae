package admission

import "maps"

func flowDerivation(v any, labels map[string]any) error {
	result := labels[stringAt(v, "result_label_ref")]
	if result == nil || !equal(at(result, "subject"), at(v, "result_subject")) || !equal(at(result, "policy"), at(v, "policy")) {
		return invalid()
	}
	unions := map[string]map[string]bool{}
	for _, field := range []string{"confidentiality_obligation_refs", "integrity_obligation_refs", "provenance_refs", "influence_refs"} {
		unions[field] = map[string]bool{}
	}
	maps.Copy(unions["provenance_refs"], set(at(v, "provenance_refs")))
	maps.Copy(unions["influence_refs"], set(at(v, "influence_refs")))
	for _, input := range array(at(v, "inputs")) {
		if err := flowDerivationInput(v, input, result, labels, unions); err != nil {
			return err
		}
	}
	for field, union := range unions {
		observed := set(at(result, field))
		if field == "confidentiality_obligation_refs" || field == "integrity_obligation_refs" {
			if !equalSet(observed, union) {
				return invalid()
			}
		} else if !subsetSet(union, observed) {
			return invalid()
		}
	}
	return nil
}

func flowDerivationInput(v, input, result any, labels map[string]any, unions map[string]map[string]bool) error {
	label := labels[stringAt(input, "label_ref")]
	if label == nil || !equal(at(label, "subject"), at(input, "subject")) || !equal(at(label, "policy"), at(v, "policy")) || flowSubjectKey(at(input, "subject")) == flowSubjectKey(at(v, "result_subject")) {
		return invalid()
	}
	if stringAt(label, "resolution_status") != termResolved && stringAt(result, "resolution_status") == termResolved {
		return invalid()
	}
	for field, union := range unions {
		maps.Copy(union, set(at(label, field)))
	}
	unions["influence_refs"][stringAt(input, "subject", "subject_ref")] = true
	return nil
}

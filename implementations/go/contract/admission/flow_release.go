package admission

func flowRelease(v any, labels map[string]any) error {
	source, result := labels[stringAt(v, "source_label_ref")], labels[stringAt(v, "result_label_ref")]
	if source == nil || result == nil || flowSubjectKey(at(v, "source_subject")) == flowSubjectKey(at(v, "result_subject")) || !equal(at(source, "subject"), at(v, "source_subject")) || !equal(at(result, "subject"), at(v, "result_subject")) || !equal(at(v, "policy"), at(source, "policy")) || !equal(at(v, "policy"), at(result, "policy")) {
		return invalid()
	}
	if stringAt(source, "resolution_status") != termResolved && stringAt(result, "resolution_status") == termResolved || !subset(stringsOf(at(source, "provenance_refs")), set(at(result, "provenance_refs"))) {
		return invalid()
	}
	influence := set(at(source, "influence_refs"))
	influence[stringAt(source, "subject", "subject_ref")] = true
	if !subsetSet(influence, set(at(result, "influence_refs"))) {
		return invalid()
	}
	if stringAt(v, termKind) == termDeclassification {
		removed, expected := set(at(v, "removed_confidentiality_obligation_refs")), set(at(source, "confidentiality_obligation_refs"))
		if !subsetSet(removed, expected) {
			return invalid()
		}
		for token := range removed {
			delete(expected, token)
		}
		return require(equalSet(expected, set(at(result, "confidentiality_obligation_refs"))) && equal(at(result, "integrity_obligation_refs"), at(source, "integrity_obligation_refs")))
	}
	return flowEndorsement(v, source, result)
}

func flowEndorsement(v, source, result any) error {
	expected, removed, added := set(at(source, "integrity_obligation_refs")), map[string]bool{}, map[string]bool{}
	for _, replacement := range array(at(v, "integrity_obligation_replacements")) {
		removed[stringAt(replacement, "source_obligation_ref")] = true
		added[stringAt(replacement, "result_obligation_ref")] = true
	}
	if !subsetSet(removed, expected) {
		return invalid()
	}
	for token := range removed {
		delete(expected, token)
	}
	for token := range added {
		expected[token] = true
	}
	return require(equalSet(expected, set(at(result, "integrity_obligation_refs"))) && equal(at(result, "confidentiality_obligation_refs"), at(source, "confidentiality_obligation_refs")))
}

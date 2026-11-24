package admission

import "strings"

func toolFeature(feature string) bool {
	return feature == termToolAffordances || feature == termScopedToolAffordances
}

func toolSupport(profile any, entries []any, supported map[string]bool) error {
	positive := map[string]bool{}
	for _, entry := range entries {
		if toolFeature(stringAt(entry, "feature")) && stringAt(entry, "support_level") != statusUnsupported {
			positive[stringAt(entry, "feature")] = true
		}
	}
	if err := toolPresence(profile, positive, supported); err != nil {
		return err
	}

	for _, entry := range entries {
		if toolFeature(stringAt(entry, "feature")) {
			if err := toolSupportEntry(profile, entry); err != nil {
				return err
			}
		}
	}
	return nil
}

func toolPresence(profile any, positive, supported map[string]bool) error {
	if len(positive) > 0 && profile == nil || profile != nil && !positive[termToolAffordances] || positive[termScopedToolAffordances] && !positive[termToolAffordances] {
		return invalid()
	}
	for _, feature := range []string{termToolAffordances, termScopedToolAffordances} {
		if positive[feature] != supported[feature] {
			return invalid()
		}
	}
	return nil
}

func toolSupportEntry(profile, entry any) error {
	for _, field := range []string{"constraint_refs", "limitation_refs", "disclosure_refs", "evidence_refs"} {
		for _, ref := range stringsOf(at(entry, field)) {
			if strings.TrimSpace(ref) == "" {
				return invalid()
			}
		}
	}
	if stringAt(entry, "support_level") == statusUnsupported {
		return nil
	}
	capacity := map[string]bool{}
	for _, field := range []string{"max_bindings_per_profile", "max_participants_per_binding"} {
		if at(profile, field) != nil {
			capacity["tool_profiles."+field] = true
		}
	}
	constraints := set(at(entry, "constraint_refs"))
	if !subsetSet(constraints, capacity) {
		return invalid()
	}
	return require(stringAt(entry, "support_level") != assuranceBounded || len(capacity) > 0 && equalSet(constraints, capacity))
}

func processorTools(v any) error {
	entries := array(at(v, "feature_support"))
	if len(rowSet(entries, "feature")) != len(entries) {
		return invalid()
	}
	positive := map[string]bool{}
	for _, entry := range entries {
		if !toolFeature(stringAt(entry, "feature")) {
			return invalid()
		}
		if stringAt(entry, "support_level") != statusUnsupported {
			positive[stringAt(entry, "feature")] = true
		}
	}
	return toolSupport(v, entries, positive)
}

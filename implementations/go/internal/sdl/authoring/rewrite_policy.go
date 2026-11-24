package authoring

// Rewrite policies through their existing owner, retaining only authored field
// presence for a transformation. Composition merges their full scope records.
func rewritePolicyReferences(value map[string]any, symbols importSymbols, namespace string) error {
	if original := object(value["augmentation_scope"]); original != nil {
		rewritten, err := rewriteAugmentation(value, symbols, namespace)
		if err != nil {
			return err
		}
		preserved, err := preserveRewrittenShape(original, rewritten, namespace == "")
		if err != nil {
			return err
		}
		value["augmentation_scope"] = preserved
	}
	if original := object(value["execution_policy"]); original != nil {
		rewritten := rewriteExecutionPolicy(original, symbols, namespace)
		preserved, err := preserveRewrittenShape(original, rewritten, namespace == "")
		if err != nil {
			return err
		}
		value["execution_policy"] = preserved
	}
	return nil
}
func preserveRewrittenShape(original, rewritten any, preserveSequences bool) (any, error) {
	if template := object(original); template != nil && object(rewritten) != nil {
		return preservePolicyMapping(template, object(rewritten), preserveSequences)
	}
	if template, ok := original.([]any); ok && preserveSequences {
		if values, sequence := rewritten.([]any); sequence {
			return preservePolicySequence(template, values)
		}
	}
	return rewritten, nil
}
func preservePolicyMapping(template, rewritten map[string]any, preserveSequences bool) (any, error) {
	result := map[string]any{}
	for key, old := range template {
		value, present := rewritten[key]
		if !present {
			return nil, invalid()
		}
		next, err := preserveRewrittenShape(old, value, preserveSequences)
		if err != nil {
			return nil, err
		}
		result[key] = next
	}
	return result, nil
}
func preservePolicySequence(template, rewritten []any) ([]any, error) {
	if len(template) != len(rewritten) {
		return nil, invalid()
	}
	result := make([]any, len(template))
	for i, value := range template {
		next, err := preserveRewrittenShape(value, rewritten[i], true)
		if err != nil {
			return nil, err
		}
		result[i] = next
	}
	return result, nil
}

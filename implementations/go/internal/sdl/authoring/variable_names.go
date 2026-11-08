package authoring

// The parent binding pass must see each child's preserved variables under
// their new identities. Data keys and pinned assets are never token rewritten.
func (c *composition) namespaceVariables(value map[string]any, namespace string, exports []any) (map[string]any, error) {
	names := map[string]string{}
	for name := range object(value[variablesSection]) {
		names[name] = qualifiedImport(namespace, name, exports)
	}
	if len(names) == 0 {
		return value, nil
	}
	rename := substitution{values: map[string]any{}, preserved: map[string]bool{}, copies: &c.copies, inline: map[string]string{}, keepUnknown: true}
	for original, qualified := range names {
		rename.values[original] = "${" + qualified + "}"
	}
	result := make(map[string]any, len(value))
	for key, item := range value {
		if key != controlAssetsSection {
			var err error
			item, err = rename.walk(item)
			if err != nil {
				return nil, err
			}
		}
		result[key] = item
	}
	for _, raw := range object(result[variationPointsField]) {
		point := object(raw)
		if point[kindField] == variationParameterKind {
			target := object(point[targetField])
			if renamed, present := names[text(target["variable"])]; present {
				target["variable"] = renamed
			}
		}
	}
	return result, nil
}

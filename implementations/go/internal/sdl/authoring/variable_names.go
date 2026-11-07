package authoring

// The parent binding pass must see each child's preserved variables under
// their new identities. Data keys and pinned assets are never token rewritten.
func namespaceVariables(value map[string]any, namespace string, exports []any) map[string]any {
	names := map[string]string{}
	for name := range object(value["variables"]) {
		names[name] = qualifiedImport(namespace, name, exports)
	}
	if len(names) == 0 {
		return value
	}
	result := make(map[string]any, len(value))
	for key, item := range value {
		if key != controlAssetsSection {
			item = renameVariableTokens(item, names)
		}
		result[key] = item
	}
	for _, raw := range object(result["variation_points"]) {
		point := object(raw)
		if point["kind"] == "parameter" {
			target := object(point["target"])
			if renamed, present := names[text(target["variable"])]; present {
				target["variable"] = renamed
			}
		}
	}
	return result
}

func renameVariableTokens(value any, names map[string]string) any {
	switch v := value.(type) {
	case string:
		return variableTokens.ReplaceAllStringFunc(v, func(token string) string {
			if renamed, present := names[token[2:len(token)-1]]; present {
				return "${" + renamed + "}"
			}
			return token
		})
	case ordered:
		return renameVariableTokens(object(v), names)
	case map[string]any:
		result := make(map[string]any, len(v))
		for key, child := range v {
			result[key] = renameVariableTokens(child, names)
		}
		return result
	case []any:
		result := make([]any, len(v))
		for i, child := range v {
			result[i] = renameVariableTokens(child, names)
		}
		return result
	default:
		return value
	}
}

package authoring

import (
	"maps"
	"slices"
	"strings"
)

func (c *composition) captureBoundExplicitness(value map[string]any, facts *importFacts, preserved map[string]bool) error {
	model, err := c.parser.newSemanticModel(facts.document)
	if err != nil {
		return err
	}
	explicitPayload := maps.Clone(value)
	delete(explicitPayload, variablesSection)
	records, err := instantiatedExplicitness(model, explicitPayload)
	if err != nil {
		return err
	}
	kept := []any{}
	for _, raw := range records {
		record := object(raw)
		preserve := false
		for _, parameter := range array(record["parameters"]) {
			parts := array(parameter)
			if len(parts) == 1 && preserved[text(parts[0])] {
				preserve = true
			}
		}
		if !preserve {
			kept = append(kept, raw)
		}
	}
	facts.explicitness = append(kept, facts.explicitness...)
	facts.document = nil
	return nil
}
func qualifyExplicitness(records []any, namespace string, symbols importSymbols) []any {
	result := []any{}
	for _, raw := range records {
		record := maps.Clone(object(raw))
		path := text(record["model_path"])
		section, _, dotted := strings.Cut(path, ".")
		if !dotted || !slices.Contains(declarationSections(), section) {
			continue
		}
		for _, name := range slices.SortedFunc(maps.Keys(symbols[section]), func(a, b string) int { return len(b) - len(a) }) {
			prefix := section + "." + name
			if path == prefix || strings.HasPrefix(path, prefix+".") || strings.HasPrefix(path, prefix+"[") {
				record["model_path"] = section + "." + symbols[section][name] + strings.TrimPrefix(path, prefix)
				break
			}
		}
		parameters := []any{}
		for _, parameter := range array(record["parameters"]) {
			parameters = append(parameters, append([]any{namespace}, array(parameter)...))
		}
		record["parameters"] = parameters
		result = append(result, record)
	}
	return result
}

func mergeExpandedExplicitness(records []any, root map[string]any) []any {
	provenance := object(root["expansion_provenance"])
	if provenance == nil {
		return records
	}
	portable := map[string]any{}
	for _, record := range array(provenance[termExplicitness]) {
		portable[text(object(record)["model_path"])] = record
	}
	prefixes := expandedDeclarationPrefixes(root, provenance)
	result := []any{}
	used := map[string]bool{}
	for _, record := range records {
		path := text(object(record)["model_path"])
		if replacement, present := portable[path]; present {
			result = append(result, replacement)
			used[path] = true
			continue
		}
		if !slices.ContainsFunc(prefixes, func(prefix string) bool { return modelPathWithin(path, prefix) }) {
			result = append(result, record)
		}
	}
	for _, record := range array(provenance[termExplicitness]) {
		if !used[text(object(record)["model_path"])] {
			result = append(result, record)
		}
	}
	return result
}

func expandedDeclarationPrefixes(root, provenance map[string]any) []string {
	prefixes := []string{}
	for _, rawImport := range array(provenance[importsField]) {
		namespace := strings.Join(stringItems(array(object(rawImport)[namespaceField])), ".")
		for _, section := range declarationSections() {
			for name := range object(root[section]) {
				if strings.HasPrefix(name, namespace+".") {
					prefixes = append(prefixes, section+"."+name)
				}
			}
		}
	}
	return prefixes
}
func modelPathWithin(path, prefix string) bool {
	return path == prefix || strings.HasPrefix(path, prefix+".") || strings.HasPrefix(path, prefix+"[")
}

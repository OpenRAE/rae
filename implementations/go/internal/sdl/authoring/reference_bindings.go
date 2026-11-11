package authoring

import (
	"slices"
)

// ReferenceBindings copies the admitted declaration index's reference aliases.
func (d *Document) ReferenceBindings() (map[string][]string, error) {
	if !d.Validated() {
		return nil, semanticInvalid()
	}
	result := map[string][]string{}
	for alias, declarations := range d.semantic.index.aliases {
		eligible := []string{}
		for address, declaration := range declarations {
			if declaration.declared {
				eligible = append(eligible, address)
			}
		}
		if len(eligible) > 0 {
			slices.Sort(eligible)
			result[alias] = eligible
		}
	}
	return result, nil
}

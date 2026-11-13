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

// ReferenceBindingsFor projects the existing resolution owner and retains
// ambiguity in each purpose's full resolution domain.
func (d *Document) ReferenceBindingsFor(purpose string) (map[string][]string, error) {
	if !d.Validated() {
		return nil, semanticInvalid()
	}
	if purpose == "declared" {
		return d.ReferenceBindings()
	}
	if purpose == "operating-scope" {
		result := map[string][]string{}
		for alias, candidates := range d.semantic.operating.aliases {
			addresses := make([]string, 0, len(candidates))
			for address := range candidates {
				addresses = append(addresses, address)
			}
			slices.Sort(addresses)
			result[alias] = addresses
		}
		return result, nil
	}
	var selected semanticPurpose
	switch purpose {
	case "observation-subject":
		selected = referenceObservation
	case "targetable":
		selected = referenceTarget
	case "action-target":
		selected = referenceActionTarget
	case "authority-anchor":
		selected = referenceAuthorityAnchor
	case "authority-scope":
		selected = referenceAuthorityScope
	default:
		return nil, invalid()
	}
	result := map[string][]string{}
	for alias := range d.semantic.index.aliases {
		resolution := d.semantic.referenceResult(alias, []semanticPurpose{selected})
		if len(resolution.eligible) > 0 {
			result[alias] = resolution.domain
		}
	}
	return result, nil
}

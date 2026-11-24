package authoring

import (
	"fmt"
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

type semanticVariationCandidate struct {
	section, owner, slot, candidate string
	collection                      bool
}

func (m *semanticModel) variationCandidate(section, owner, slot, candidate string, collection bool) (bool, error) {
	addresses := m.variationReferences(owner, section)
	if len(addresses) != 1 {
		return false, nil
	}
	key := semanticVariationCandidate{section, addresses[0], slot, candidate, collection}
	if valid, known := m.probeCache[key]; known {
		return valid, nil
	}
	valid, err := m.probeVariation(key)
	if err == nil {
		if m.probeCache == nil {
			m.probeCache = map[semanticVariationCandidate]bool{}
		}
		m.probeCache[key] = valid
	}
	return valid, err
}
func (m *semanticModel) probeVariation(key semanticVariationCandidate) (bool, error) {
	root := maps.Clone(m.root)
	owners := maps.Clone(object(root[key.section]))
	name := strings.TrimPrefix(key.owner, key.section+".")
	owner := maps.Clone(object(owners[name]))
	if owner == nil {
		return false, nil
	}
	// Slot names came from the closed reference/collection tables. This
	// bridge writes only the admitted owner's serialized slot.
	field := strings.TrimPrefix(key.slot, key.section+".")
	owner[field] = key.candidate
	if key.collection {
		if current := object(object(owners[name])[field]); current != nil {
			value, known := current[key.candidate]
			if !known {
				value = ""
			}
			owner[field] = map[string]any{key.candidate: value}
		} else {
			owner[field] = []any{key.candidate}
		}
	}
	owners[name] = owner
	root[key.section] = owners
	root[variationPointsField] = map[string]any{}
	data, err := encode(root, jsonWorkingLimit(m.parser.limits.MaxComposedBytes, m.parser.limits.MaxComposedNodes), false)
	if err != nil {
		return probeRefusal(err)
	}
	if m.document.contract == expandedContract {
		validationInput := maps.Clone(root)
		delete(validationInput, "expansion_provenance")
		bound := composition{parser: m.parser}
		_, err = bound.validateBound(validationInput)
	} else {
		err = m.parser.models.CheckSDLConstruction(m.document.contract, "#", data, modelLimits(data))
	}
	if err != nil {
		return probeRefusal(err)
	}
	probe := *m.document
	probe.data, probe.validated, probe.semantic = data, false, nil
	probe.modelData = data
	model, err := m.parser.newSemanticModel(&probe)
	if err != nil {
		return probeRefusal(err)
	}
	collector := newSemanticCollector(&probe)
	if err = model.check(&collector); err != nil {
		return false, err
	}
	return len(collector.errors) == 0, nil
}
func probeRefusal(err error) (bool, error) {
	if category, known := fault.CategoryOf(err); known && category == fault.InvalidInput {
		return false, nil
	}
	return false, err
}

type semanticSelectionVariable struct{ point, member string }

func (m *semanticModel) variationMatches(ref string) []int {
	rendered := strings.TrimPrefix(ref, variationPointsField+".")
	var matches []int
	for i, point := range m.variations {
		local := point.name[strings.LastIndexByte(point.name, '.')+1:]
		if rendered == point.name || rendered == local {
			matches = append(matches, i)
		}
	}
	return matches
}
func (v semanticVariationCheck) relations() {
	members, names := v.members()
	for _, name := range names {
		member := members[name]
		required := v.relationPairs(name, member.Requires)
		excluded := v.relationPairs(name, member.Excludes)
		for pair := range required {
			if excluded[pair] {
				v.report(fmt.Sprintf("member '%s' has contradictory relations", name))
				break
			}
		}
	}
}
func (v semanticVariationCheck) relationPairs(member string, relations []semanticSelectionRelation) map[semanticSelectionVariable]bool {
	pairs := map[semanticSelectionVariable]bool{}
	for _, relation := range relations {
		matches := v.model.variationMatches(relation.Point)
		if len(matches) != 1 {
			problem := "undefined"
			if len(matches) > 1 {
				problem = "ambiguous"
			}
			v.report(fmt.Sprintf("member '%s' relation point is %s", member, problem))
			continue
		}
		point := v.model.variations[matches[0]]
		target := semanticVariationCheck{model: v.model, point: point}
		members, _ := target.members()
		for _, name := range relation.Members {
			if _, known := members[name]; !known {
				v.report(fmt.Sprintf("member '%s' relation member is undefined", member))
			}
			pairs[semanticSelectionVariable{point.name, name}] = true
		}
	}
	return pairs
}

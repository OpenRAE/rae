package authoring

import (
	"maps"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
)

type provenancePathChange struct {
	before, after string
	removed       bool
}
type provenancePathChanges struct{ pointers, models []provenancePathChange }

func reconcileSelectedProvenance(original, payload map[string]any) {
	changes := provenancePathChanges{}
	for name, raw := range object(original[nodesSection]) {
		node := object(object(payload[nodesSection])[name])
		for _, section := range []string{nodesSection, infrastructureField} {
			changes.declaration(section, name, name, node == nil)
		}
		if node != nil {
			prefix := "/nodes/" + jsonpointer.EscapeToken(name) + "/runtime"
			model := "nodes." + name + ".runtime"
			changes.runtime(object(object(raw)[runtimeField]), object(node[runtimeField]), prefix, prefix, model, model, sdlrules.RuntimeFamilies())
		}
	}
	for _, section := range []string{accountsSection, contentField, persistentVolumesField, generatedArtifactsField, relationshipsField, propositionsField, assertionsSection, evidenceRequirementsSection} {
		for name, raw := range object(original[section]) {
			retained := object(object(payload[section])[name])
			changes.declaration(section, name, name, retained == nil)
			if retained != nil && (section == persistentVolumesField || section == generatedArtifactsField) {
				changes.consumers(section, name, array(object(raw)[termConsumers]), array(retained[termConsumers]))
			}
		}
	}
	reconcileProvenancePaths(payload, changes)
}
func reconcileProvenancePaths(payload map[string]any, changes provenancePathChanges) {
	provenance := object(payload["expansion_provenance"])
	for _, field := range []string{termCapabilityConstraints, termParameterDerivations, termRealizationDesignations, termRealizationConstraints} {
		provenance[field] = remapProvenanceRecords(array(provenance[field]), fieldPointerField, changes.pointers, []string{"/"})
	}
	provenance[termExplicitness] = remapProvenanceRecords(array(provenance[termExplicitness]), "model_path", changes.models, []string{".", "["})
}
func (c *provenancePathChanges) declaration(section, before, after string, removed bool) {
	pointer := "/" + section + "/"
	model := section + "."
	c.pointers = append(c.pointers, provenancePathChange{pointer + jsonpointer.EscapeToken(before), pointer + jsonpointer.EscapeToken(after), removed})
	c.models = append(c.models, provenancePathChange{model + before, model + after, removed})
}
func (c *provenancePathChanges) runtime(original, selected map[string]any, beforePointer, afterPointer, beforeModel, afterModel string, specs []sdlrules.RuntimeCollection) {
	for _, spec := range specs {
		positions := map[string]int{}
		rows := array(selected[spec.Collection])
		for i, row := range rows {
			positions[text(object(row)[spec.Identity])] = i
		}
		for i, row := range array(original[spec.Collection]) {
			after, retained := positions[text(object(row)[spec.Identity])]
			bp := beforePointer + "/" + spec.Collection + "/" + strconv.Itoa(i)
			ap := afterPointer + "/" + spec.Collection + "/" + strconv.Itoa(after)
			bm := beforeModel + "." + spec.Collection + "[" + strconv.Itoa(i) + "]"
			am := afterModel + "." + spec.Collection + "[" + strconv.Itoa(after) + "]"
			c.pointers = append(c.pointers, provenancePathChange{bp, ap, !retained})
			c.models = append(c.models, provenancePathChange{bm, am, !retained})
			if retained {
				c.runtime(object(row), object(rows[after]), bp, ap, bm, am, spec.Children)
			}
		}
	}
}
func (c *provenancePathChanges) consumers(section, name string, original, selected []any) {
	identity := func(raw any) string {
		row := object(raw)
		return text(row[termNode]) + "\x00" + text(row["mount_destination"])
	}
	positions := map[string]int{}
	for i, row := range selected {
		positions[identity(row)] = i
	}
	for i, row := range original {
		after, retained := positions[identity(row)]
		pointer := "/" + section + "/" + jsonpointer.EscapeToken(name) + "/consumers/"
		model := section + "." + name + ".consumers"
		c.pointers = append(c.pointers, provenancePathChange{pointer + strconv.Itoa(i), pointer + strconv.Itoa(after), !retained})
		c.models = append(c.models, provenancePathChange{model + "[" + strconv.Itoa(i) + "]", model + "[" + strconv.Itoa(after) + "]", !retained})
	}
}
func remapProvenanceRecords(records []any, key string, changes []provenancePathChange, separators []string) []any {
	slices.SortStableFunc(changes, func(a, b provenancePathChange) int { return len(b.before) - len(a.before) })
	result := []any{}
	for _, raw := range records {
		record := object(raw)
		path, retain := text(record[key]), true
		for _, change := range changes {
			match := path == change.before
			for _, separator := range separators {
				match = match || strings.HasPrefix(path, change.before+separator)
			}
			if match {
				path, retain = change.after+strings.TrimPrefix(path, change.before), !change.removed
				break
			}
		}
		if retain {
			retained := maps.Clone(record)
			retained[key] = path
			result = append(result, retained)
		}
	}
	return result
}

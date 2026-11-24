package authoring

import (
	"fmt"
	"slices"
	"strings"
)

type declaration struct {
	target, authority, action, declared bool
	kind                                string
	node, parent                        string
	value, owner                        map[string]any
	tokens                              []string
	collisionKind                       string
}

// Objective subjects include world declarations and truth claims about them.
func (d declaration) objectiveSubject() bool {
	return d.action || d.kind == propositionsField || d.kind == assertionsSection
}

type declarationIndex struct {
	aliases      map[string]map[string]declaration
	addresses    map[string]bool
	collision    bool
	declarations map[string]declaration
	collisions   []string
	order        map[string][]string
}

func (d *declarationIndex) add(address, alias string, category declaration) {
	category.declared = category.declared || category.target
	if previous, present := d.declarations[address]; present {
		if previous.collisionKind != category.collisionKind || !slices.Equal(previous.tokens, category.tokens) {
			d.collision = true
			message := fmt.Sprintf("Canonical address '%s' collides between %s declaration at %s and %s declaration at %s", address, previous.collisionKind, strings.Join(previous.tokens, "."), category.collisionKind, strings.Join(category.tokens, "."))
			if !slices.Contains(d.collisions, message) {
				d.collisions = append(d.collisions, message)
			}
		}
		return
	}
	d.declarations[address] = category
	d.addresses[address] = true
	for _, name := range []string{address, alias} {
		if name == "" {
			continue
		}
		if d.aliases[name] == nil {
			d.aliases[name] = map[string]declaration{}
		}
		if _, present := d.aliases[name][address]; !present {
			d.aliases[name][address] = category
		}
	}
}
func sectionCategory(section string) declaration {
	category := sectionFlags(section)
	category.kind = section
	return category
}
func sectionFlags(section string) declaration {
	switch section {
	case nodesSection, infrastructureField, featuresSection, contentField, accountsSection, identityDomainsField, identityForestsField, identityFacadesField, deploymentTenantsField, deploymentCellsField, persistentVolumesField, generatedArtifactsField, forwardingSection, agentsSection, entitiesField, relationshipsField:
		return declaration{target: true, authority: true, action: true}
	case actionsSection, boundariesSection, behaviorSection:
		return declaration{target: true, authority: true}
	case propositionsField, assertionsSection, conditionsSection, injectsSection, eventsSection, scriptsField, storiesField, variationPointsField:
		return declaration{target: true}
	case outcomeRulesSection:
		return declaration{}
	default:
		return declaration{declared: true}
	}
}
func (d *declarationIndex) ambiguous(reference string, authority bool) bool {
	if variable(reference) {
		return false
	}
	candidates := d.aliases[reference]
	if !authority {
		return len(candidates) > 1
	}
	count, eligible := 0, false
	for _, candidate := range candidates {
		if candidate.target {
			count++
		}
		eligible = eligible || candidate.authority
	}
	return eligible && count > 1
}
func rejectImportAmbiguities(value map[string]any) error {
	index := indexDeclarations(value)
	for _, section := range []string{agentsSection, behaviorSection} {
		for _, raw := range object(value[section]) {
			owner := object(raw)
			for _, binding := range object(owner[controlContextField]) {
				if index.ambiguous(text(object(binding)[declarationRefField]), false) {
					return invalid()
				}
			}
		}
	}
	return index.rejectBehaviorAmbiguities(object(value[behaviorSection]))
}
func (d *declarationIndex) rejectBehaviorAmbiguities(specs map[string]any) error {
	for _, raw := range specs {
		spec := object(raw)
		for _, binding := range object(spec[toolAffordancesField]) {
			if d.ambiguous(text(object(binding)[toolRefField]), false) {
				return invalid()
			}
		}
		for _, reference := range array(spec[authorityScopeRefsField]) {
			if d.ambiguous(text(reference), true) {
				return invalid()
			}
		}
	}
	return nil
}

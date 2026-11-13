package processor

import (
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// Canonical declaration resolution stays with SDL. This projection only maps
// eligible declarations to compiler-owned runtime addresses.
func (state *compilerState) runtimeAddresses(refs []string) []string {
	return state.runtimeAddressesFor(refs, "declared")
}
func (state *compilerState) runtimeAddressesFor(refs []string, purpose string) []string {
	aliases := state.input.aliases
	if purpose != "declared" {
		if state.input.references == nil {
			state.input.references = map[string]map[string][]string{}
		}
		var loaded bool
		aliases, loaded = state.input.references[purpose]
		if !loaded {
			var err error
			aliases, err = sdl.ReferenceBindingsFor(state.input.scenario, purpose)
			if err != nil {
				state.err = err
				return nil
			}
			state.input.references[purpose] = aliases
		}
	}
	result := []string{}
	for _, ref := range dedupe(refs) {
		candidates := aliases[ref]
		if len(candidates) != 1 {
			continue
		}
		if address := state.runtimeDeclaration(candidates[0]); address != "" {
			result = append(result, address)
		}
	}
	return dedupe(result)
}
func (state *compilerState) runtimeDeclaration(canonical string) string {
	if state.runtimeReferences == nil {
		state.buildRuntimeReferences()
	}
	return state.runtimeReferences[canonical]
}
func (state *compilerState) buildRuntimeReferences() {
	result := map[string]string{}
	model := state.input.model
	state.nodeRuntimeReferences(result)
	groups := []struct{ section, root, kind string }{
		{termContent, termProvision, termContent}, {termAccounts, termProvision, "account"}, {termConditions, "template", "condition"}, {termFeatures, "template", "feature"}, {termActionContracts, termParticipant, termActionContract}, {termObservationBoundaries, termParticipant, termObservationBoundary}, {termOutcomeInterpretationRules, termParticipant, termOutcomeInterpretationRule}, {termBehaviorSpecifications, termParticipant, termBehaviorSpecification}, {termGeneratedArtifacts, termProvision, termGeneratedArtifact}, {termPersistentVolumes, termProvision, termPersistentVolume},
	}
	for _, group := range groups {
		for _, name := range state.names(group.section) {
			result[group.section+"."+name] = state.address(group.root, group.kind, name)
		}
	}
	state.contentRuntimeReferences(result)
	specifications := fieldValue(model.BehaviorSpecifications)
	for _, name := range orderedNames(specifications, state.names(termBehaviorSpecifications)) {
		specification := specifications[name]
		for id := range fieldValue(specification.ToolAffordances) {
			result["behavior_specifications."+name+".tool_affordances."+id] = state.address(termParticipant, termBehaviorSpecification, name, "tool-affordance", id)
		}
		for id := range fieldValue(specification.ParticipantInjectDeliveries) {
			result["behavior_specifications."+name+".participant_inject_deliveries."+id] = state.address(termParticipant, termBehaviorSpecification, name, "inject-delivery", id)
		}
	}
	state.runtimeReferences = result
}
func (state *compilerState) nodeRuntimeReferences(result map[string]string) {
	nodes := fieldValue(state.input.model.Nodes)
	for _, name := range orderedNames(nodes, state.names(termNodes)) {
		result["nodes."+name] = state.nodeAddress(name)
		result["infrastructure."+name] = state.nodeAddress(name)
		for _, service := range fieldValue(nodes[name].Services) {
			serviceName := rawString(fieldValue(service.Name))
			if serviceName != "" {
				result["nodes."+name+".services."+serviceName] = state.address(termProvision, termNode, name, "service", serviceName)
			}
		}
	}
}
func (state *compilerState) contentRuntimeReferences(result map[string]string) {
	content := fieldValue(state.input.model.Content)
	for _, name := range orderedNames(content, state.names(termContent)) {
		for _, item := range fieldValue(content[name].Items) {
			itemName := fieldValue(item.Name)
			if itemName != "" {
				result["content."+name+".items."+itemName] = state.address(termProvision, termContent, name, "items", itemName)
			}
		}
	}
}

type referenceFindingContext struct {
	owner, domain, code, label string
}

func (state *compilerState) namedReferences(section, root, kind string, refs []string, context referenceFindingContext) ([]string, []diagnostic.Diagnostic) {
	result := []string{}
	findings := []diagnostic.Diagnostic{}
	known := state.known(section)
	for _, ref := range dedupe(refs) {
		if !known[ref] {
			findings = append(findings, compileDiagnostic(context.code+"-unbound", context.domain, context.owner, "Reference '"+ref+"' does not resolve to a defined "+context.label+"."))
			continue
		}
		result = append(result, state.address(root, kind, ref))
	}
	return result, findings
}
func (state *compilerState) known(section string) map[string]bool {
	if state.knownNames == nil {
		state.knownNames = map[string]map[string]bool{}
	}
	if entries, ok := state.knownNames[section]; ok {
		return entries
	}
	entries := map[string]bool{}
	for _, name := range state.names(section) {
		entries[name] = true
	}
	state.knownNames[section] = entries
	return entries
}

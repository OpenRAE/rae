package authoring

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

const semanticRefusalCode = "sdl-semantic-invalid"

func semanticInvalid() error { return fault.New(fault.InvalidInput, semanticRefusalCode, nil) }

// The reference always checks materialized semantics, including during format.
// Authored formatting deliberately stops at construction and import checks.
func (p *Parser) checkFormatPhase(document *Document) error {
	if document.contract != materializedContract {
		return nil
	}
	err := p.checkMaterializedFormat(document)
	if category, known := fault.CategoryOf(err); known && category == fault.InvalidInput {
		return fault.New(fault.InvalidInput, semanticRefusalCode, err)
	}
	return err
}
func (p *Parser) checkMaterializedFormat(document *Document) error {
	if err := p.models.CheckSDLLocalSemantics(document.contract, document.data, modelLimits(document.data)); err != nil {
		return err
	}
	value, err := p.modelValue(document)
	if err != nil {
		return err
	}
	check := materializedChecks{parser: p, value: value, index: indexDeclarations(value), serviceOwners: indexServiceOwners(value), nodeOrder: document.source.View().Child(nodesSection).Keys()}
	check.scopes = newScopeQueries(p, document.contract, value)
	if err = check.index.effectTargets(value); err != nil {
		return err
	}
	for _, pass := range []func() error{check.nodes, check.infrastructure, check.sections, check.contentAndAccounts, check.propositions, check.timeModel, check.runtimeNetwork, check.runtimeServices, check.forwardingReferences, check.cloudResources, check.variables, check.relationships, check.topology, check.enterpriseIdentity, check.descriptorProfiles, check.tenancy, check.agents, check.interactiveAccess, check.participantBehavior, check.controlContext, check.mixedControl, check.participantRelationships, check.injectDeliveries, check.autonomous, check.participantOutcomes, check.objectives, check.workflows, check.evidence, check.execution} {
		if err = pass(); err != nil {
			return err
		}
	}
	return nil
}

type materializedChecks struct {
	parser        *Parser
	value         map[string]any
	index         *declarationIndex
	serviceOwners map[string]map[string]bool
	nodeOrder     []string
	scopes        *scopeQueries
}

func (c materializedChecks) nodes() error {
	for name, raw := range object(c.value[nodesSection]) {
		node := object(raw)
		parts := strings.Split(name, ".")
		if len(parts[len(parts)-1]) > 35 {
			return semanticInvalid()
		}
		if err := c.nodeBindings(node); err != nil {
			return err
		}
		if err := c.nodePlatform(node); err != nil {
			return err
		}
	}
	return nil
}
func (c materializedChecks) nodeBindings(node map[string]any) error {
	for _, section := range []string{featuresSection, conditionsSection, injectsSection} {
		definitions := object(c.value[section])
		for reference, role := range object(node[section]) {
			if _, present := definitions[reference]; !present {
				return semanticInvalid()
			}
			if text(role) != "" && !variable(text(role)) {
				if _, present := object(node["roles"])[text(role)]; !present {
					return semanticInvalid()
				}
			}
		}
	}
	return nil
}

func referencesPresent(references []any, definitions map[string]any) error {
	for _, raw := range references {
		reference := text(raw)
		if variable(reference) {
			continue
		}
		if _, present := definitions[reference]; !present {
			return semanticInvalid()
		}
	}
	return nil
}
func (c materializedChecks) infrastructure() error {
	nodes := object(c.value[nodesSection])
	infrastructure := object(c.value[infrastructureField])
	dependencies := map[string][]string{}
	for name, raw := range infrastructure {
		if _, present := nodes[name]; !present {
			return semanticInvalid()
		}
		entry := object(raw)
		if err := c.infrastructureEntry(name, entry); err != nil {
			return err
		}
		if err := referencesPresent(array(entry["dependencies"]), infrastructure); err != nil {
			return err
		}
		for _, raw := range array(entry["dependencies"]) {
			if !variable(text(raw)) {
				dependencies[name] = append(dependencies[name], text(raw))
			}
		}
	}
	if graph.HasCycle(dependencies) {
		return semanticInvalid()
	}
	return nil
}
func (c materializedChecks) sections() error {
	if err := c.featureDependencies(); err != nil {
		return err
	}
	entities := map[string]any{}
	collectEntities(object(c.value[entitiesField]), "", entities)
	for _, raw := range entities {
		if err := referencesPresent(array(object(raw)[eventsSection]), object(c.value[eventsSection])); err != nil {
			return err
		}
	}
	if err := c.injectEntities(entities); err != nil {
		return err
	}

	if err := c.narrativeReferences(); err != nil {
		return err
	}
	for _, raw := range object(c.value[nodesSection]) {
		for _, role := range object(object(raw)["roles"]) {
			if err := referencesPresent(array(object(role)[entitiesField]), entities); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c materializedChecks) featureDependencies() error {
	features := object(c.value[featuresSection])
	dependencies := map[string][]string{}
	for name, raw := range features {
		refs := array(object(raw)["dependencies"])
		if err := referencesPresent(refs, features); err != nil {
			return err
		}
		for _, reference := range refs {
			if !variable(text(reference)) {
				dependencies[name] = append(dependencies[name], text(reference))
			}
		}
	}
	if graph.HasCycle(dependencies) {
		return semanticInvalid()
	}
	return nil
}
func (c materializedChecks) narrativeReferences() error {
	for _, raw := range object(c.value[eventsSection]) {
		if err := referencesPresent(array(object(raw)[injectsSection]), object(c.value[injectsSection])); err != nil {
			return err
		}
	}
	for _, raw := range object(c.value[scriptsField]) {
		for reference := range object(object(raw)[eventsSection]) {
			if err := referencesPresent([]any{reference}, object(c.value[eventsSection])); err != nil {
				return err
			}
		}
	}
	for _, raw := range object(c.value[storiesField]) {
		if err := referencesPresent(array(object(raw)[scriptsField]), object(c.value[scriptsField])); err != nil {
			return err
		}
	}
	return nil
}
func collectEntities(entities map[string]any, prefix string, result map[string]any) {
	for name, raw := range entities {
		qualified := prefix + name
		result[qualified] = raw
		collectEntities(object(object(raw)[entitiesField]), qualified+".", result)
	}
}

func (c materializedChecks) injectEntities(entities map[string]any) error {
	for _, raw := range object(c.value[injectsSection]) {
		inject := object(raw)
		if from := text(inject["from_entity"]); from != "" {
			if err := referencesPresent([]any{from}, entities); err != nil {
				return err
			}
		}
		if err := referencesPresent(array(inject["to_entities"]), entities); err != nil {
			return err
		}
	}
	return nil
}

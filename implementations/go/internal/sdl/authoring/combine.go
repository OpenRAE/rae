package authoring

import (
	"slices"
	"strings"
)

func declarationSections() []string {
	return []string{
		nodesSection, infrastructureField, featuresSection, conditionsSection, propositionsField, assertionsSection, entitiesField, injectsSection, eventsSection, scriptsField, storiesField, contentField, controlAssetsSection, generatedArtifactsField, persistentVolumesField, accountsSection, identityDomainsField, identityForestsField, identityFacadesField, deploymentTenantsField, deploymentCellsField, relationshipsField, agentsSection, actionsSection, boundariesSection, outcomeRulesSection, behaviorSection, evidenceRequirementsSection, "time_domains", "clocks", "time_domain_mappings", "time_progression_policies", temporalConstraintsSection, objectivesSection, workflowsSection, variablesSection, variationPointsField,
	}
}
func validateExports(value, descriptor map[string]any) error {
	for section, raw := range object(descriptor["exports"]) {
		if !slices.Contains(declarationSections(), section) && section != forwardingSection {
			return importError("export-invalid")
		}
		names := exportNames(value, section)
		for _, name := range array(raw) {
			if !localQualified(text(name)) || !names[text(name)] {
				return importError("export-invalid")
			}
		}
	}
	return nil
}
func exportNames(value map[string]any, section string) map[string]bool {
	names := map[string]bool{}
	if section == forwardingSection {
		for _, agent := range array(value[section]) {
			names[text(object(agent)["forwarding_agent_id"])] = true
		}
		return names
	}
	for name := range object(value[section]) {
		names[name] = true
	}
	if section == entitiesField {
		collectEntityNames(object(value[section]), "", names)
	}
	return names
}
func collectEntityNames(entities map[string]any, prefix string, names map[string]bool) {
	for name, raw := range entities {
		qualified := prefix + name
		names[qualified] = true
		collectEntityNames(object(object(raw)[entitiesField]), qualified+".", names)
	}
}
func (c *composition) combine(parent, incoming map[string]any, namespace string, descriptor map[string]any) error {
	if err := rejectImportAmbiguities(incoming); err != nil {
		return err
	}
	exports := object(descriptor["exports"])
	var err error
	incoming, err = c.namespaceVariables(incoming, namespace, array(exports[variablesSection]))
	if err != nil {
		return err
	}
	if err := c.composePolicies(parent, incoming, namespace, descriptor); err != nil {
		return err
	}
	for _, section := range declarationSections() {
		if err := c.combineSection(parent, object(incoming[section]), section, namespace, array(exports[section])); err != nil {
			return err
		}
	}
	return c.combineAgents(parent, array(incoming[forwardingSection]), namespace, array(exports[forwardingSection]))
}
func (c *composition) combineSection(parent, incoming map[string]any, section, namespace string, exports []any) error {
	current := object(parent[section])
	if current == nil {
		current = map[string]any{}
	}
	for name, value := range incoming {
		qualified := qualifiedImport(namespace, name, exports)
		if err := c.budget.CheckNamespace(qualified); err != nil {
			return err
		}
		if _, exists := current[qualified]; exists {
			return importError("collision")
		}
		current[qualified] = value
	}
	parent[section] = current
	return nil
}
func qualifiedImport(namespace, name string, exports []any) string {
	if slices.ContainsFunc(exports, func(raw any) bool { return raw == name }) {
		return namespace + "." + name
	}
	return namespace + ".__private." + name
}
func (c *composition) combineAgents(parent map[string]any, incoming []any, namespace string, exports []any) error {
	current := append([]any{}, array(parent[forwardingSection])...)
	identities := map[string]bool{}
	for _, agent := range current {
		identities[text(object(agent)["forwarding_agent_id"])] = true
	}
	for _, raw := range incoming {
		agent := object(raw)
		qualified := qualifiedImport(namespace, text(agent["forwarding_agent_id"]), exports)
		if err := c.budget.CheckNamespace(qualified); err != nil {
			return err
		}
		if identities[qualified] {
			return importError("collision")
		}
		identities[qualified] = true
		agent["forwarding_agent_id"] = qualified
		current = append(current, agent)
	}
	parent[forwardingSection] = current
	return nil
}

func localQualified(name string) bool {
	if name == "" || len(name) > 2048 {
		return false
	}
	parts := strings.Split(name, ".")
	for i, part := range parts {
		if part == privateSegment && i < len(parts)-1 {
			continue
		}
		if !variable("${" + part + "}") {
			return false
		}
	}
	return true
}

package authoring

import (
	"slices"
	"strings"
)

func declarationSections() []string {
	return []string{
		nodesSection, "infrastructure", featuresSection, conditionsSection, "propositions", "assertions", "entities", injectsSection, "events", "scripts", "stories", "content", controlAssetsSection, "generated_artifacts", "persistent_volumes", "accounts", "identity_domains", "identity_forests", "identity_facades", "deployment_tenants", "deployment_cells", "relationships", agentsSection, "action_contracts", "observation_boundaries", "outcome_interpretation_rules", behaviorSection, "evidence_requirements", "time_domains", "clocks", "time_domain_mappings", "time_progression_policies", "temporal_constraints", "objectives", "workflows", "variables", "variation_points",
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
	if section == "entities" {
		collectEntityNames(object(value[section]), "", names)
	}
	return names
}
func collectEntityNames(entities map[string]any, prefix string, names map[string]bool) {
	for name, raw := range entities {
		qualified := prefix + name
		names[qualified] = true
		collectEntityNames(object(object(raw)["entities"]), qualified+".", names)
	}
}
func (c *composition) combine(parent, incoming map[string]any, namespace string, descriptor map[string]any) error {
	exports := object(descriptor["exports"])
	incoming = namespaceVariables(incoming, namespace, array(exports["variables"]))
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
	if len(current) > 0 {
		parent[section] = current
	}
	return nil
}
func qualifiedImport(namespace, name string, exports []any) string {
	if slices.ContainsFunc(exports, func(raw any) bool { return raw == name }) {
		return namespace + "." + name
	}
	return namespace + ".__private." + name
}
func (c *composition) combineAgents(parent map[string]any, incoming []any, namespace string, exports []any) error {
	current := array(parent[forwardingSection])
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
	if len(current) > 0 {
		parent[forwardingSection] = current
	}
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

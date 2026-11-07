package authoring

import (
	"slices"
	"strings"
)

func declarationSections() []string {
	return []string{
		"nodes", "infrastructure", "features", "conditions", "propositions", "assertions", "entities", "injects", "events", "scripts", "stories", "content", "control_context_assets", "generated_artifacts", "persistent_volumes", "accounts", "identity_domains", "identity_forests", "identity_facades", "deployment_tenants", "deployment_cells", "relationships", "agents", "action_contracts", "observation_boundaries", "outcome_interpretation_rules", "behavior_specifications", "evidence_requirements", "time_domains", "clocks", "time_domain_mappings", "time_progression_policies", "temporal_constraints", "objectives", "workflows", "variables", "variation_points",
	}
}
func validateExports(value, descriptor map[string]any) error {
	for section, raw := range object(descriptor["exports"]) {
		if !slices.Contains(declarationSections(), section) && section != "forwarding_agents" {
			return importError("export-invalid")
		}
		names := map[string]bool{}
		if section == "forwarding_agents" {
			for _, agent := range array(value[section]) {
				names[text(object(agent)["forwarding_agent_id"])] = true
			}
		} else {
			for name := range object(value[section]) {
				names[name] = true
			}
		}
		if section == "entities" {
			collectEntityNames(object(value[section]), "", names)
		}
		for _, name := range array(raw) {
			if !localQualified(text(name)) || !names[text(name)] {
				return importError("export-invalid")
			}
		}
	}
	return nil
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
	for _, section := range declarationSections() {
		current := object(parent[section])
		if current == nil {
			current = map[string]any{}
		}
		for name, value := range object(incoming[section]) {
			qualified := namespace + ".__private." + name
			if slices.ContainsFunc(array(exports[section]), func(raw any) bool { return raw == name }) {
				qualified = namespace + "." + name
			}
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
	}
	current := array(parent["forwarding_agents"])
	identities := map[string]bool{}
	for _, agent := range current {
		identities[text(object(agent)["forwarding_agent_id"])] = true
	}
	for _, raw := range array(incoming["forwarding_agents"]) {
		agent := object(raw)
		name := text(agent["forwarding_agent_id"])
		qualified := namespace + ".__private." + name
		if slices.ContainsFunc(array(exports["forwarding_agents"]), func(raw any) bool { return raw == name }) {
			qualified = namespace + "." + name
		}
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
		parent["forwarding_agents"] = current
	}
	return nil
}

func localQualified(name string) bool {
	if name == "" || len(name) > 2048 {
		return false
	}
	parts := strings.Split(name, ".")
	for i, part := range parts {
		if part == "__private" && i < len(parts)-1 {
			continue
		}
		if !variable("${" + part + "}") {
			return false
		}
	}
	return true
}

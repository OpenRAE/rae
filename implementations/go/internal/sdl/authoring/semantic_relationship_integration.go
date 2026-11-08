package authoring

import "fmt"

func (m *semanticModel) platformByID(ref string) (string, *semanticPlatform) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		for i := range node.runtime.Platforms {
			if node.runtime.Platforms[i].ID == ref {
				return node.name, &node.runtime.Platforms[i]
			}
		}
	}
	return "", nil
}
func (m *semanticModel) integrationEndpoint(c *semanticCollector, owner semanticOwner, label, field, ref string) (string, *semanticPlatform) {
	if !concreteReference(ref) {
		return "", nil
	}
	node, app := m.platformByID(ref)
	if app == nil {
		c.report(owner, fmt.Sprintf("%s service_integration %s '%s' does not resolve to a platform application on any node", label, field, ref))
	}
	return node, app
}
func (m *semanticModel) checkRelationshipIntegrations(c *semanticCollector) {
	for _, row := range m.relationships {
		integration := row.services.integration
		if integration == nil {
			continue
		}
		owner, label := semanticOwner{relationshipsField, row.name}, fmt.Sprintf("Relationship '%s'", row.name)
		m.integrationEndpoint(c, owner, label, "consumer_ref", integration.Consumer)
		node, engine := m.integrationEndpoint(c, owner, label, "engine_ref", integration.Engine)
		if engine != nil && concreteReference(integration.Principal) {
			m.integrationPrincipal(c, owner, label, node, engine.Authorization, integration.Principal)
		}
	}
}
func (m *semanticModel) integrationPrincipal(c *semanticCollector, owner semanticOwner, label, node, selected, ref string) {
	runtime := m.nodes[m.nodeIndex[node]].runtime
	foundStore := false
	for _, authorization := range runtime.Authorizations {
		if concreteReference(selected) && authorization.ID != selected {
			continue
		}
		foundStore = true
		for _, principal := range authorization.Principals {
			if principal.ID == ref {
				return
			}
		}
	}
	if concreteReference(selected) && !foundStore {
		return
	}
	scope := "an app_authorization principal"
	if concreteReference(selected) {
		scope = fmt.Sprintf("authorization '%s'", selected)
	}
	c.report(owner, fmt.Sprintf("%s service_integration auth_principal_ref '%s' does not resolve to %s on the engine application's node '%s'", label, ref, scope, node))
}

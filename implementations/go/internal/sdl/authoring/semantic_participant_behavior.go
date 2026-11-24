package authoring

import "fmt"

func (m *semanticModel) checkParticipantBehavior(c *semanticCollector) {
	m.checkControlContext(c)
	for _, finding := range m.temporal {
		c.report(semanticOwner{finding.Owner.Section, finding.Owner.Name}, finding.Message)
	}
	m.checkParticipantReferences(c)
	m.checkBehaviorSpecs(c)
	m.checkResourceOwners(c)
	m.checkAffordanceTools(c)
	m.checkDeliveries(c)
	m.checkParticipantInteractions(c)
	m.checkBehaviorAuthority(c)
	m.checkMixedControl(c)
}
func (m *semanticModel) checkParticipantReferences(c *semanticCollector) {
	m.checkParticipantAgentReferences(c)
	m.checkRelatedActions(c)
	m.checkBoundaryViews(c)
}
func (m *semanticModel) checkParticipantAgentReferences(c *semanticCollector) {
	for _, row := range m.agents {
		owner := semanticOwner{agentsSection, row.name}
		m.checkParticipantActions(c, row)
		for _, ref := range row.boundaries {
			if !variable(ref) && !m.definitions[boundariesSection][ref] {
				c.report(owner, fmt.Sprintf("Agent '%s' observation_boundary '%s' does not reference a declared observation_boundary", row.name, ref))
			}
		}
	}
}
func (m *semanticModel) checkParticipantActions(c *semanticCollector, row semanticAgent) {
	if len(m.definitions[actionsSection]) == 0 {
		return
	}
	for _, ref := range row.actions {
		if !variable(ref) && !m.definitions[actionsSection][ref] {
			c.report(semanticOwner{agentsSection, row.name}, fmt.Sprintf("Agent '%s' action '%s' does not reference a declared action_contract", row.name, ref))
		}
	}
}

package authoring

func (m *semanticModel) checkStatefulResources(c *semanticCollector) {
	for _, finding := range m.stateful {
		c.report(semanticOwner{finding.Owner.Section, finding.Owner.Name}, finding.Message)
	}
}

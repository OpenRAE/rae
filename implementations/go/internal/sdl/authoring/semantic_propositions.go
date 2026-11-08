package authoring

import "fmt"

func (m *semanticModel) checkPropositions(c *semanticCollector) {
	m.checkPropositionReferences(c)
	m.checkAssertionReferences(c)
	m.checkConditionPropositions(c)
}
func (m *semanticModel) checkPropositionReferences(c *semanticCollector) {
	propositions, _ := m.transport.Propositions.Value()
	for _, name := range m.keys(propositionsField) {
		value := propositions[name]
		owner, label := semanticOwner{propositionsField, name}, "Proposition '"+name+"'"
		for _, reference := range fieldValue(value.Subjects) {
			m.namedReference(c, owner, label, "subject", reference, referenceObservation)
		}
		for _, reference := range fieldValue(value.EvidenceRequirements) {
			if !variable(reference) && !m.definitions[evidenceRequirementsSection][reference] {
				c.report(owner, fmt.Sprintf("%s evidence_requirement '%s' not in evidence_requirements section", label, reference))
			}
		}
	}
}
func (m *semanticModel) checkAssertionReferences(c *semanticCollector) {
	assertions, _ := m.transport.Assertions.Value()
	for _, name := range m.keys(assertionsSection) {
		reference := fieldValue(assertions[name].Proposition)
		if !variable(reference) && !m.definitions[propositionsField][reference] {
			c.report(semanticOwner{assertionsSection, name}, fmt.Sprintf("Assertion '%s' proposition '%s' not in propositions section", name, reference))
		}
	}
}
func (m *semanticModel) checkConditionPropositions(c *semanticCollector) {
	conditions, _ := m.transport.Conditions.Value()
	for _, name := range m.keys(conditionsSection) {
		reference := fieldValue(conditions[name].Proposition)
		if reference != "" && !variable(reference) && !m.definitions[propositionsField][reference] {
			c.report(semanticOwner{conditionsSection, name}, fmt.Sprintf("Condition '%s' proposition '%s' not in propositions section", name, reference))
		}
	}
}

package authoring

import "fmt"

func (m *semanticModel) checkEffectTargets(c *semanticCollector) {
	values := fieldValue(m.transport.ActionContracts)
	for _, name := range m.keys(actionsSection) {
		for _, effect := range fieldValue(values[name].Effects) {
			label := fmt.Sprintf("Action contract '%s' effect '%s'", name, fieldValue(effect.EffectId))
			for _, ref := range fieldValue(effect.TargetRefs) {
				// An undeclared token is observation information. A registered identity
				// remains subject to the shared action-target purpose policy.
				if len(m.index.aliases[ref]) != 0 {
					m.namedReference(c, semanticOwner{actionsSection, name}, label, "target_ref", ref, referenceActionTarget)
				}
			}
		}
	}
}
func (m *semanticModel) checkParticipantInteractions(c *semanticCollector) {
	m.checkEffectTargets(c)
	values := fieldValue(m.transport.ActionContracts)
	for _, name := range m.keys(actionsSection) {
		for index, interaction := range fieldValue(values[name].Interactions) {
			owner, label := semanticOwner{actionsSection, name}, fmt.Sprintf("Action contract '%s' interaction[%d]", name, index)
			m.namedReference(c, owner, label, targetField, fieldValue(interaction.Target), referenceActionTarget)
			for _, ref := range fieldValue(interaction.SharedStateRefs) {
				m.namedReference(c, owner, label, "shared_state_ref", ref, referenceSharedState)
			}
		}
	}
}
func (p *Parser) checkModuleEffectTargets(document *Document) error {
	model, err := p.newSemanticModel(document)
	if err != nil {
		return err
	}
	if len(model.index.collisions) != 0 {
		return semanticInvalid()
	}
	collector := newSemanticCollector(document)
	model.checkEffectTargets(&collector)
	if len(collector.errors) != 0 {
		return &semanticError{findings: collector.errors}
	}
	return nil
}

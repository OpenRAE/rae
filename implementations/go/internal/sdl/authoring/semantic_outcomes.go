package authoring

import (
	"encoding/json"
	"fmt"
)

type semanticLocalOutcome struct {
	Criteria []struct {
		ID     string `json:"criterion_id"`
		Source string `json:"source_id"`
		Effect string `json:"effect_id"`
	} `json:"criteria"`
}

func (m *semanticModel) outcomeFacts() error {
	m.localOutcomes = map[string]semanticLocalOutcome{}
	for name, row := range fieldValue(m.transport.OutcomeInterpretationRules) {
		raw := fieldValue(row.LocalOutcome)
		if len(raw) == 0 || string(raw) == nullType {
			continue
		}
		var local semanticLocalOutcome
		if err := json.Unmarshal(raw, &local); err != nil {
			return invalid()
		}
		m.localOutcomes[name] = local
	}
	return nil
}
func (m *semanticModel) checkOutcomes(c *semanticCollector) {
	effects := m.declaredEffects()
	values := fieldValue(m.transport.OutcomeInterpretationRules)
	for _, name := range m.keys(outcomeRulesSection) {
		row := values[name]
		m.checkLocalEffects(c, name, effects)
		for _, source := range fieldValue(row.SourceBindings) {
			m.outcomeReference(c, name, sourceField, string(fieldValue(source.SourceLayer)), fieldValue(source.Ref))
		}
		for _, target := range fieldValue(row.TargetBindings) {
			m.outcomeReference(c, name, targetField, string(fieldValue(target.TargetLayer)), fieldValue(target.Ref))
		}
	}
}
func (m *semanticModel) declaredEffects() map[string]map[string]bool {
	effects := map[string]map[string]bool{}
	for name, action := range fieldValue(m.transport.ActionContracts) {
		effects[name] = map[string]bool{}
		for _, effect := range fieldValue(action.Effects) {
			effects[name][fieldValue(effect.EffectId)] = true
		}
	}
	return effects
}
func (m *semanticModel) checkLocalEffects(c *semanticCollector, name string, effects map[string]map[string]bool) {
	sources := map[string]string{}
	for _, source := range fieldValue(fieldValue(m.transport.OutcomeInterpretationRules)[name].SourceBindings) {
		sources[fieldValue(source.SourceId)] = fieldValue(source.Ref)
	}
	for _, criterion := range m.localOutcomes[name].Criteria {
		if available, known := effects[sources[criterion.Source]]; known && !available[criterion.Effect] {
			c.report(semanticOwner{outcomeRulesSection, name}, fmt.Sprintf("Outcome interpretation rule '%s' criterion '%s' references undefined effect '%s'", name, criterion.ID, criterion.Effect))
		}
	}
}
func (m *semanticModel) outcomeReference(c *semanticCollector, name, side, layer, ref string) {
	section, term := outcomeLayerSection(side, layer)
	if section == "" || variable(ref) || m.definitions[section][ref] {
		return
	}
	c.report(semanticOwner{outcomeRulesSection, name}, fmt.Sprintf("Outcome interpretation rule '%s' %s '%s' references undefined %s", name, side, ref, term))
}
func outcomeLayerSection(side, layer string) (string, string) {
	switch layer {
	case "participant_action_outcome":
		if side == sourceField {
			return actionsSection, "action contract"
		}
	case "objective_result":
		return objectivesSection, "objective"
	case "workflow_result":
		return workflowsSection, "workflow"
	}
	return "", ""
}

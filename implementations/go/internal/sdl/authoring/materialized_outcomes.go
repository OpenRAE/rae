package authoring

func (c materializedChecks) participantOutcomes() error {
	for _, raw := range object(c.value[outcomeRulesSection]) {
		if err := c.outcomeRule(object(raw)); err != nil {
			return err
		}
	}
	return nil
}
func (c materializedChecks) outcomeRule(rule map[string]any) error {
	sources := map[string]map[string]any{}
	for _, side := range []string{sourceField, targetField} {
		for _, raw := range array(rule[side+"_bindings"]) {
			binding := object(raw)
			if side == sourceField {
				sources[text(binding["source_id"])] = binding
			}
			section := outcomeLayerSection(side, text(binding[side+"_layer"]))
			if section != "" {
				if err := referencesPresent([]any{binding["ref"]}, object(c.value[section])); err != nil {
					return err
				}
			}
		}
	}
	return c.localOutcomeEffects(object(rule["local_outcome"]), sources)
}
func outcomeLayerSection(side, layer string) string {
	switch layer {
	case "participant_action_outcome":
		if side == sourceField {
			return actionsSection
		}
	case "objective_result":
		return objectivesSection
	case "workflow_result":
		return workflowsSection
	}
	return ""
}
func (c materializedChecks) localOutcomeEffects(local map[string]any, sources map[string]map[string]any) error {
	byAction := map[string]map[string]bool{}
	for _, raw := range array(local["criteria"]) {
		criterion := object(raw)
		actionRef := text(sources[text(criterion["source_id"])]["ref"])
		action := object(object(c.value[actionsSection])[actionRef])
		if action == nil {
			continue
		}
		effects, found := byAction[actionRef]
		if !found {
			effects = map[string]bool{}
			for _, effect := range array(action["effects"]) {
				effects[text(object(effect)["effect_id"])] = true
			}
			byAction[actionRef] = effects
		}
		if !effects[text(criterion["effect_id"])] {
			return semanticInvalid()
		}
	}
	return nil
}

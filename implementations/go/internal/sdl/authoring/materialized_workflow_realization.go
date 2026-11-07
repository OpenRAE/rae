package authoring

func (c materializedChecks) workflowRealization(step map[string]any) error {
	if err := c.workflowAction(text(step["procedure_ref"]), "procedure"); err != nil {
		return err
	}
	for _, ref := range array(step["allowed_action_families"]) {
		if err := c.workflowAction(text(ref), "aggregate"); err != nil {
			return err
		}
	}
	if err := c.workflowScaffolds(step); err != nil {
		return err
	}
	if err := c.workflowAffordances(step); err != nil {
		return err
	}
	for _, ref := range concreteRefs(array(step["capability_refs"])) {
		if !c.parser.authority.Permits("participant-runtime-behavior-features", ref) && !c.parser.authority.Permits("participant-runtime-interaction-features", ref) {
			return semanticInvalid()
		}
	}
	for _, ref := range concreteRefs(array(step["fact_binding_refs"])) {
		if err := c.parser.authority.CheckScope("workflows.steps.fact_binding_refs", ref); err != nil {
			return err
		}
	}
	return nil
}
func (c materializedChecks) workflowAction(ref, granularity string) error {
	if ref == "" || variable(ref) {
		return nil
	}
	action := object(object(c.value[actionsSection])[ref])
	if action == nil || action["behavioral_granularity"] != granularity {
		return semanticInvalid()
	}
	return nil
}

func (c materializedChecks) workflowScaffolds(step map[string]any) error {
	for _, ref := range concreteRefs(array(step["scaffold_refs"])) {
		boundary := object(object(c.value[boundariesSection])[ref])
		found := false
		for _, raw := range array(boundary[viewRulesField]) {
			switch object(raw)["boundary_class"] {
			case "instruction", "starter_file", "scaffold_instruction", "subtask_guidance":
				found = true
			}
		}
		if !found {
			return semanticInvalid()
		}
	}

	return nil
}
func (c materializedChecks) workflowAffordances(step map[string]any) error {
	for _, ref := range concreteRefs(array(step["tool_affordance_refs"])) {
		found := false
		for name, raw := range object(c.value[behaviorSection]) {
			for id := range object(object(raw)["tool_affordances"]) {
				found = found || ref == "behavior_specifications."+name+".tool_affordances."+id
			}
		}
		if !found {
			return semanticInvalid()
		}
	}

	return nil
}

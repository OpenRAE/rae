package authoring

import "fmt"

func (w *semanticWorkflowCheck) realization(name string, step semanticWorkflowStep) {
	w.actionReference(name, "procedure_ref", step.Procedure, "procedure")
	for _, ref := range step.Actions {
		w.actionReference(name, "allowed_action_families", ref, "aggregate")
	}
	w.scaffolds(name, step.Scaffolds)
	for _, ref := range step.Tools {
		if !variable(ref) && !w.model.toolAffordance(ref) {
			w.report(fmt.Sprintf("%s references undefined tool affordance '%s'", w.label(name), ref))
		}
	}
	for _, ref := range step.Capabilities {
		if !variable(ref) && !w.model.parser.authority.Permits("participant-runtime-behavior-features", ref) && !w.model.parser.authority.Permits("participant-runtime-interaction-features", ref) {
			w.report(fmt.Sprintf("%s references ungoverned participant capability '%s': it is neither a listed term nor an accepted extension term of the participant runtime behavior or interaction feature vocabularies", w.label(name), ref))
		}
	}
	for _, ref := range step.Facts {
		if !variable(ref) && w.model.parser.authority.CheckScope("workflows.steps.fact_binding_refs", ref) != nil {
			w.report(fmt.Sprintf("%s references ungoverned runtime-fact binding '%s': it is neither a listed term nor an accepted extension term of the workflow step fact-binding vocabulary", w.label(name), ref))
		}
	}
}
func (w *semanticWorkflowCheck) actionReference(name, field, ref, granularity string) {
	if ref == "" || variable(ref) {
		return
	}
	value, present := fieldValue(w.model.transport.ActionContracts)[ref]
	if !present {
		w.report(fmt.Sprintf("%s %s references undefined action contract '%s'", w.label(name), field, ref))
	} else if string(fieldValue(value.BehavioralGranularity)) != granularity {
		w.report(fmt.Sprintf("%s %s action contract '%s' must have %s behavioral granularity", w.label(name), field, ref, granularity))
	}
}
func (m *semanticModel) toolAffordance(ref string) bool {
	for _, name := range m.keys(behaviorSection) {
		for id := range fieldValue(fieldValue(m.transport.BehaviorSpecifications)[name].ToolAffordances) {
			if ref == behaviorSection+"."+name+".tool_affordances."+id {
				return true
			}
		}
	}
	return false
}
func (w *semanticWorkflowCheck) scaffolds(name string, refs []string) {
	values := fieldValue(w.model.transport.ObservationBoundaries)
	for _, ref := range refs {
		if variable(ref) {
			continue
		}
		boundary, present := values[ref]
		if !present {
			w.report(fmt.Sprintf("%s references undefined scaffold observation boundary '%s'", w.label(name), ref))
			continue
		}
		found := false
		for _, rule := range fieldValue(boundary.ViewRules) {
			switch string(fieldValue(rule.BoundaryClass)) {
			case "instruction", "starter_file", "scaffold_instruction", "subtask_guidance":
				found = true
			}
		}
		if !found {
			w.report(fmt.Sprintf("%s scaffold observation boundary '%s' does not declare an instruction, starter-file, scaffold-instruction, or subtask-guidance view rule", w.label(name), ref))
		}
	}
}

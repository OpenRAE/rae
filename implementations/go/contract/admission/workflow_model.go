package admission

import "slices"

type stepShape struct{ required, forbidden []string }

func workflowShape(v any) error {
	if err := workflowMode(v); err != nil {
		return err
	}
	shape := workflowFields(stringAt(v, "type"))
	for _, field := range shape.required {
		if !stepFieldSet(v, field) {
			return invalid()
		}
	}
	for _, field := range shape.forbidden {
		if stepFieldSet(v, field) {
			return invalid()
		}
	}
	if stringAt(v, "type") == "parallel" {
		return require(len(array(at(v, termBranches))) >= 2 && unique(stringsOf(at(v, termBranches))))
	}
	if stringAt(v, "type") == termSwitch {
		return require(len(array(at(v, stepCases))) > 0)
	}
	return nil
}
func workflowMode(v any) error {
	mode := stringAt(v, "execution_mode")
	if mode == "" {
		mode = "scripted"
	}
	kind := stringAt(v, "type")
	if mode != "scripted" && (kind != termObjective && kind != "retry" || stringAt(v, "procedure_ref") != "") {
		return invalid()
	}
	scaffolds := len(array(at(v, "scaffold_refs"))) > 0
	actions := len(array(at(v, "allowed_action_families"))) > 0
	if mode != termScaffolded && (scaffolds || actions) {
		return invalid()
	}
	if mode == termScaffolded && !scaffolds && !actions && len(array(at(v, "tool_affordance_refs"))) == 0 {
		return invalid()
	}
	for _, field := range []string{"scaffold_refs", "allowed_action_families", "tool_affordance_refs", "capability_refs", "fact_binding_refs"} {
		values := stringsOf(at(v, field))
		if !unique(values) || slices.ContainsFunc(values, sdlBlank) {
			return invalid()
		}
	}
	return nil
}
func stepFieldSet(v any, field string) bool {
	value := at(v, field)
	switch field {
	case stepWhen, termMaxAttempts:
		return value != nil
	case termBranches, stepCases:
		return len(array(value)) > 0
	default:
		return text(value) != ""
	}
}
func workflowFields(kind string) stepShape {
	switch kind {
	case termObjective:
		return stepShape{[]string{termObjective, stepSuccess}, []string{stepNext, stepExhausted, stepWhen, stepThen, termElse, termBranches, stepJoin, termMaxAttempts}}
	case "decision":
		return stepShape{[]string{stepWhen, stepThen, termElse}, []string{termObjective, stepNext, stepSuccess, stepFailure, stepExhausted, termBranches, stepJoin, termMaxAttempts, termCompensateWith}}
	case termSwitch:
		return stepShape{[]string{stepCases, termDefault}, []string{termObjective, stepNext, stepSuccess, stepFailure, stepExhausted, stepWhen, stepThen, termElse, termBranches, stepJoin, termWorkflow, termMaxAttempts, termCompensateWith}}
	case "parallel":
		return stepShape{[]string{termBranches, stepJoin}, []string{termObjective, stepWhen, stepNext, stepSuccess, stepExhausted, stepThen, termElse, termMaxAttempts, termCompensateWith}}
	case stepJoin:
		return stepShape{[]string{stepNext}, []string{termObjective, stepSuccess, stepFailure, stepExhausted, stepWhen, stepThen, termElse, termBranches, stepJoin, termMaxAttempts, termCompensateWith}}
	case "retry":
		return stepShape{[]string{termObjective, termMaxAttempts, stepSuccess}, []string{stepNext, stepWhen, stepFailure, stepThen, termElse, termBranches, stepJoin, termCompensateWith}}
	case "call":
		return stepShape{[]string{termWorkflow, stepSuccess}, []string{termObjective, stepNext, stepExhausted, stepWhen, stepThen, termElse, stepCases, termDefault, termBranches, stepJoin, termMaxAttempts}}
	default:
		return stepShape{nil, []string{termObjective, stepNext, stepWhen, stepSuccess, stepFailure, stepExhausted, stepThen, termElse, stepCases, termDefault, termBranches, stepJoin, termWorkflow, termMaxAttempts, termCompensateWith}}
	}
}

const (
	stepWhen      = "when"
	stepCases     = "cases"
	stepJoin      = "join"
	stepFailure   = "on_failure"
	stepSuccess   = "on_success"
	stepExhausted = "on_exhausted"
	stepThen      = "then"
	stepNext      = "next"
)

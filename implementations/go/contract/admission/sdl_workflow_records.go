package admission

import "strings"

func sdlServiceMaterializationFields(v any) error {
	return require(nonblankSDLRefs(v, "ordering_content_refs", "readback_assertion_refs", "evidence_requirement_refs", "observation_boundary_refs"))
}

func sdlObjective(v any) error {
	return require(stringAt(v, "owner") != "" || stringAt(v, "assigned_participant") != "")
}
func sdlCompensationPolicy(v any) error {
	return require(fieldsUnique(v, "on") && text(defaultMember(v, "order", "reverse_completion")) == "reverse_completion" && (text(defaultMember(v, "mode", "disabled")) != "automatic" || len(array(at(v, "on"))) > 0))
}
func sdlWorkflowPredicate(v any) error {
	return require(len(array(at(v, "assertions")))+len(array(at(v, "objectives")))+len(array(at(v, "steps"))) > 0)
}
func sdlMaterializationSpecification(v any) error {
	mechanism := stringAt(v, "profile", "mechanism")
	return require((mechanism == termMaterializationSpecification || strings.HasPrefix(mechanism, "x-")) && fieldsUnique(v, "locked_input_ids"))
}

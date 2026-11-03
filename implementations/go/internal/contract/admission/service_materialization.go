package admission

import (
	"regexp"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

var variableReference = regexp.MustCompile(`^\$\{(?:(?:[a-z0-9][a-z0-9_-]{0,63}|__private)\.)*[a-z0-9][a-z0-9_-]{0,63}\}$`)

func variableRef(v string) bool { return variableReference.MatchString(v) }
func declaredRefs(refs any, declarations any) bool {
	for _, ref := range stringsOf(refs) {
		if _, ok := object(declarations)[ref]; !ok && !variableRef(ref) {
			return false
		}
	}
	return true
}
func serviceMaterialization(i validation.Invocation) error {
	v := sdlInstance(i)
	for name, item := range object(at(v, "content")) {
		binding := at(item, "service_materialization")
		if binding == nil {
			continue
		}
		if stringAt(binding, termSchemaVersion) == "domain-profile-binding/v1" {
			continue
		}
		if err := serviceTarget(v, item, binding); err != nil {
			return err
		}
		if !declaredRefs(at(binding, "ordering_content_refs"), at(v, "content")) || set(at(binding, "ordering_content_refs"))[name] || !declaredRefs(at(binding, "evidence_requirement_refs"), at(v, "evidence_requirements")) || !declaredRefs(at(binding, "observation_boundary_refs"), at(v, "observation_boundaries")) {
			return invalid()
		}
		if err := serviceReadback(v, name, binding); err != nil {
			return err
		}
		if err := serviceTenancy(v, binding); err != nil {
			return err
		}
	}
	return nil
}
func serviceTarget(v, item, binding any) error {
	reference := stringAt(binding, "target_service_ref")
	if variableRef(reference) {
		return nil
	}
	for name, node := range object(at(v, "nodes")) {
		for _, service := range array(at(node, "services")) {
			if stringAt(service, termName) != "" && reference == "nodes."+name+".services."+stringAt(service, termName) {
				return require(name == stringAt(item, "target"))
			}
		}
	}
	return invalid()
}
func serviceReadback(v any, name string, binding any) error {
	for _, ref := range stringsOf(at(binding, "readback_assertion_refs")) {
		if variableRef(ref) {
			continue
		}
		assertion := at(v, "assertions", ref)
		if assertion == nil || stringAt(assertion, "role") != "postcondition" {
			return invalid()
		}
		proposition := at(v, "propositions", stringAt(assertion, "proposition"))
		if proposition == nil {
			continue
		}
		if stringAt(proposition, "basis") != "observed_state" || !containsSubject(at(proposition, "subjects"), name) || !subset(stringsOf(at(binding, "evidence_requirement_refs")), set(at(proposition, "evidence_requirements"))) {
			return invalid()
		}
	}
	for _, ref := range stringsOf(at(binding, "observation_boundary_refs")) {
		if boundary := at(v, "observation_boundaries", ref); boundary != nil && !containsSubject(at(boundary, "observable_refs"), name) {
			return invalid()
		}
	}
	return nil
}
func containsSubject(refs any, name string) bool {
	values := set(refs)
	return values[name] || values["content."+name]
}
func serviceTenancy(v, binding any) error {
	ref := stringAt(binding, "shared_service_relationship_ref")
	if ref == "" || variableRef(ref) {
		return nil
	}
	relationship := at(v, "relationships", ref)
	return require(relationship != nil && stringAt(relationship, "type") == "uses_shared_service" && at(relationship, "shared_service") != nil && equal(at(relationship, "target"), at(binding, "target_service_ref")) && stringAt(relationship, "shared_service", "mutable_state_owner") != postureNone && stringAt(relationship, "shared_service", "reset_generation_owner") != postureNone)
}

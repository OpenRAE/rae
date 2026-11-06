package admission

import "github.com/OpenRAE/rae/implementations/go/contract/validation"

func behavioralCatalog(i validation.Invocation) error {
	v := i.Instance
	if !unique(rowIDs(at(v, "bibliography"), "source_id")) || !unique(rowIDs(at(v, "claim_surfaces"), termSurfaceID)) || !keyed(at(v, "relations"), fieldRelationID) || !keyed(at(v, "worked_examples"), "example_id") {
		return invalid()
	}
	sources, relations := rowSet(at(v, "bibliography"), "source_id"), keySet(at(v, "relations"))
	for _, relation := range object(at(v, "relations")) {
		if !subset(stringsOf(at(relation, "source_refs")), sources) {
			return invalid()
		}
		if err := relationModel(relation); err != nil {
			return err
		}
	}
	for _, surface := range array(at(v, "claim_surfaces")) {
		if !subset(stringsOf(at(surface, "intended_relation_ids")), relations) || !subset(stringsOf(at(surface, "prohibited_relation_ids")), relations) {
			return invalid()
		}
	}
	return exampleModels(v)
}
func exampleModels(v any) error {
	for _, example := range object(at(v, "worked_examples")) {
		for _, field := range []string{"left_system", "right_system"} {
			if err := exampleSystem(at(example, field)); err != nil {
				return err
			}
		}
	}
	return nil
}
func exampleSystem(v any) error {
	states := set(at(v, "states"))
	if !fieldsUnique(v, "states") || !states[stringAt(v, "initial_state")] {
		return invalid()
	}
	for _, transition := range array(at(v, termTransitions)) {
		if !states[stringAt(transition, "source")] || !states[stringAt(transition, "target")] {
			return invalid()
		}
	}
	return nil
}
func relationModel(v any) error {
	signature := at(v, "transition_signature")
	if (stringAt(signature, "applicability") == notApplicable) != (at(signature, "not_applicable_rationale") != nil) {
		return invalid()
	}
	assurance := at(v, "assurance")
	if err := assuranceImplementation(assurance); err != nil {
		return err
	}
	if stringAt(assurance, "proof_status") == assuranceModelChecked && stringAt(assurance, "model_check_status") != assuranceModelChecked {
		return invalid()
	}
	conformance, realization := stringAt(assurance, "backend_conformance_status"), stringAt(assurance, "backend_realization_status")
	if (conformance == assuranceConformant || conformance == assuranceBounded) && realization != assuranceRealized && realization != statusPartial {
		return invalid()
	}
	return require(stringAt(assurance, "definition_status") != statusFuture || !positiveAssurance(assurance))
}
func assuranceImplementation(v any) error {
	explicit, positive := false, false
	for _, field := range []string{"checker_status", "runtime_enforcement_status", "backend_realization_status"} {
		status := text(defaultMember(v, field, notApplicable))
		explicit = explicit || status != notApplicable
		positive = positive || status == statusImplemented || status == statusPartial || status == assuranceEnforced || status == assuranceRealized
	}
	if !explicit {
		return nil
	}
	aggregate := stringAt(v, "implementation_status")
	if positive {
		return require(aggregate == statusImplemented || aggregate == statusPartial)
	}
	return require(aggregate == "not-implemented")
}
func positiveAssurance(v any) bool {
	for field, positive := range map[string][]string{
		"implementation_status": {statusImplemented, statusPartial}, "test_status": {statusTested, assuranceBounded}, "proof_status": {assuranceProved, assuranceModelChecked}, "checker_status": {statusImplemented, statusPartial}, "model_check_status": {assuranceModelChecked}, "runtime_enforcement_status": {assuranceEnforced, statusPartial}, "backend_declaration_status": {assuranceDeclared}, "backend_realization_status": {assuranceRealized, statusPartial}, "backend_conformance_status": {assuranceConformant, assuranceBounded},
	} {
		for _, status := range positive {
			if stringAt(v, field) == status {
				return true
			}
		}
	}
	return false
}

package admission

import (
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func invocationRoot(i validation.Invocation) any {
	if i.Root != nil {
		return i.Root
	}
	return i.Instance
}
func (e *Validator) decisionRules() map[string]definition {
	return map[string]definition{
		"decision-surface-entry-reference-agreement":           {check: decisionV1},
		"decision-surface-presentation-not-lifecycle-evidence": {check: decisionV1},
		"decision-surface-sem226-item-exposure-agreement":      {check: decisionV1},
		"decision-surface-v2-plane-separation":                 {check: e.decisionV2},
		"decision-surface-v2-exact-cut-policy":                 {check: e.decisionV2},
		"decision-surface-v2-explicit-memory-scope":            {check: e.decisionV2},
		"decision-surface-v2-delivery-before-selection":        {check: e.decisionV2},
	}
}
func decisionView(v any) error {
	if !fieldsUnique(v, "visible_context_refs", "affordance_refs", fieldEvidenceRefs, "provenance_refs", "marking_definition_refs", "semantic_limitations") {
		return invalid()
	}
	entries := array(at(v, "action_entries"))
	if len(rowSet(entries, "entry_id")) != len(entries) || len(rowSet(entries, "action_contract_address")) != len(entries) {
		return invalid()
	}
	affordances := map[string]bool{}
	for _, entry := range entries {
		if !fieldsUnique(entry, "eligibility_reason_refs", "constraint_refs", "support_refs", "affordance_refs", "realization_refs") {
			return invalid()
		}
		if (stringAt(entry, "eligibility") == termEligible) != (len(array(at(entry, "eligibility_reason_refs"))) == 0) || stringAt(entry, "support") == "supported" && len(array(at(entry, "support_refs"))) == 0 {
			return invalid()
		}
		maps.Copy(affordances, set(at(entry, "affordance_refs")))
	}
	if !subset(stringsOf(at(v, "affordance_refs")), affordances) {
		return invalid()
	}
	return decisionForm(at(v, "form"), entries)
}

func decisionExposed(v any) map[string]bool {
	result := set(at(v, "visible_context_refs"))
	maps.Copy(result, rowSet(at(v, "action_entries"), "action_contract_address"))
	maps.Copy(result, set(at(v, "affordance_refs")))
	return result
}
func exposureBasis(v any) error {
	if !fieldsUnique(v, "source_marking_definition_refs", "result_marking_definition_refs", "source_provenance_refs", "result_provenance_refs", fieldEvidenceRefs, "provenance_refs", "loss_and_limitations") {
		return invalid()
	}
	operation := stringAt(v, "operation")
	transformed := slices.Contains([]string{"masking", termRedaction, termTransformation}, operation)
	if (transformed || !equal(at(v, "source_ref"), at(v, termItemRef))) && at(v, "transformation_rule_ref") == nil {
		return invalid()
	}
	if operation == termRedaction && at(v, "redaction_policy_ref") == nil || operation == termDeclassification && at(v, "declassification_basis_ref") == nil {
		return invalid()
	}
	if at(v, "declassification_basis_ref") == nil {
		if !subset(stringsOf(at(v, "source_marking_definition_refs")), set(at(v, "result_marking_definition_refs"))) || !subset(stringsOf(at(v, "source_provenance_refs")), set(at(v, "result_provenance_refs"))) {
			return invalid()
		}
	}
	for _, field := range []string{"source_provenance_refs", "result_provenance_refs"} {
		if !subset(stringsOf(at(v, field)), set(at(v, "provenance_refs"))) {
			return invalid()
		}
	}

	return nil
}
func exposureCarried(binding, owner any) bool {
	for _, field := range []string{fieldEvidenceRefs, "provenance_refs"} {
		if !subset(stringsOf(at(binding, field)), set(at(owner, field))) {
			return false
		}
	}
	return true
}
func decisionV1(i validation.Invocation) error {
	v := invocationRoot(i)
	if err := decisionView(v); err != nil {
		return err
	}
	bindings := array(at(v, "exposure_bindings"))
	if len(rowSet(bindings, termItemRef)) != len(bindings) || !equalSet(rowSet(bindings, termItemRef), decisionExposed(v)) {
		return invalid()
	}
	for _, binding := range bindings {
		if err := exposureBasis(binding); err != nil {
			return err
		}
		if !matchingFields(binding, v, fieldParticipantAddress, fieldEpisodeID, "audience_scope_ref", "observation_point", "observation_order", "projection_policy_ref", "projection_policy_revision", "exposure_policy_ref") || !exposureCarried(binding, v) || !subset(stringsOf(at(binding, "result_marking_definition_refs")), set(at(v, "marking_definition_refs"))) {
			return invalid()
		}
		if realized := at(binding, "realization"); realized != nil {
			if !fieldsUnique(realized, fieldEvidenceRefs, "provenance_refs", "limitations") || !equal(at(realized, termItemRef), at(binding, termItemRef)) || numericGreater(at(realized, "delivery_order"), at(binding, "observation_order")) || !exposureCarried(realized, v) {
				return invalid()
			}
		}
	}

	return nil
}
func decisionForm(form any, entries []any) error {
	if !fieldsUnique(form, "allowed_action_contract_addresses", "candidate_entry_ids", "constraint_refs", "default_disclosure_refs", "normalization_disclosure_refs", "omission_disclosure_refs", "loss_disclosure_refs") {
		return invalid()
	}
	switch stringAt(form, "surface_form") {
	case "candidate_action_set":
		return require(subset(stringsOf(at(form, "candidate_entry_ids")), rowSet(entries, "entry_id")))
	case "constrained_form":
		for _, entry := range entries {
			if equal(at(entry, "entry_id"), at(form, "action_entry_id")) {
				return require(equal(at(entry, "selection_shape_ref"), at(form, "argument_shape_ref")))
			}
		}
		return invalid()
	case "open_ended_generation":
		if !subset(stringsOf(at(form, "allowed_action_contract_addresses")), rowSet(entries, "action_contract_address")) {
			return invalid()
		}
		for _, entry := range entries {
			if set(at(form, "allowed_action_contract_addresses"))[stringAt(entry, "action_contract_address")] && !equal(at(entry, "selection_shape_ref"), at(form, "argument_shape_ref")) {
				return invalid()
			}
		}
	default:
		return invalid()
	}
	return nil
}

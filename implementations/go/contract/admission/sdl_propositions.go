package admission

import (
	"regexp"
	"slices"
)

var behaviorExtensionKey = regexp.MustCompile(`^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*\z`)

func propositionShape(v any) error {
	if !fieldsUnique(v, "subjects", "evidence_requirements") {
		return invalid()
	}
	if stringAt(v, "basis") == basisObservedState && len(array(at(v, "evidence_requirements"))) == 0 {
		return invalid()
	}
	threshold := at(v, "threshold")
	if stringAt(v, "quantifier") == "at_least" {
		n, ok := integer(threshold)
		return require(ok && n > 0 && n <= len(array(at(v, "subjects"))))
	}
	return require(threshold == nil)
}
func stringPredicateShape(v any) error {
	expected, source := at(v, "expected"), at(v, "expected_from")
	if (expected == nil) == (source == nil) {
		return invalid()
	}
	membership := slices.Contains([]string{"in", "not_in"}, stringAt(v, "operator"))
	if source != nil {
		return require(!membership)
	}
	items, list := expected.([]any)
	if membership != list {
		return invalid()
	}
	return require(!list || len(items) > 0 && unique(stringsOf(items)))
}
func behaviorReferences(v any) error {
	if sdlBlank(stringAt(v, "semantic_version")) || sdlBlank(text(defaultMember(v, "extension_policy", "governed-extension"))) {
		return invalid()
	}
	for _, field := range []string{"behavior_mode", "realization_profile_ref"} {
		if at(v, field) != nil && sdlBlank(stringAt(v, field)) {
			return invalid()
		}
	}
	for _, field := range []string{"participant_refs", "participant_role_refs", "action_contract_refs", "observation_boundary_refs", "outcome_interpretation_rule_refs", fieldAuthorityScopeRefs, "backend_feature_support_refs", "evidence_contract_refs"} {
		refs := stringsOf(at(v, field))
		if !unique(refs) || slices.ContainsFunc(refs, sdlBlank) {
			return invalid()
		}
	}
	for key := range object(at(v, "extensions")) {
		if !behaviorExtensionKey.MatchString(key) {
			return invalid()
		}
	}
	return nil
}

const (
	fieldAuthorityScopeRefs = "authority_scope_refs"
	basisObservedState      = "observed_state"
)

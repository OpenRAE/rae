package admission

import (
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) planningRules() map[string]definition {
	return map[string]definition{
		"run-allocation-condition-assignments-valid": {check: allocationAssignments},
		"experiment-binding-source-joins-valid":      {check: bindingSources},
		"run-plan-exactly-one-run-count-source": {check: func(i validation.Invocation) error {
			return require((at(i.Instance, "allocation") == nil) != (at(i.Instance, "target_run_count") == nil) && keyed(at(i.Instance, "red_variant_selections"), "variant_id"))
		}},
		"experiment-spec-blocking-factors-declared": {check: func(i validation.Invocation) error {
			return require(subset(stringsOf(at(i.Instance, "run_plan", "allocation", "blocking_factors")), keySet(at(i.Instance, "factors"))))
		}},
		"experiment-spec-condition-factor-levels-declared": {check: func(i validation.Invocation) error {
			return conditionLevels(at(i.Instance, "factors"), at(i.Instance, "run_plan", "allocation", "condition_assignments"))
		}},
		"binding-descriptors-canonical-targets-injective":       {check: func(i validation.Invocation) error { return bindingTargets(at(i.Instance, "descriptors")) }},
		"experiment-selection-treatment-identity-valid":         {check: selectionIdentity},
		"claim-bearing-study-analysis-plan-required":            {check: studyRequired},
		"adaptive-difficulty-study-validity-treatment-required": {check: adaptiveStudy},
		"difficulty-policy-registry-valid":                      {check: difficultyRegistry},
	}
}
func keySet(v any) map[string]bool {
	keys := map[string]bool{}
	for key := range object(v) {
		keys[key] = true
	}
	return keys
}
func conditionLevels(factors, assignments any) error {
	for _, assignment := range object(assignments) {
		for id, level := range object(at(assignment, "factor_levels")) {
			if !set(at(object(factors)[id], "levels"))[text(level)] {
				return invalid()
			}
		}
	}
	return nil
}
func targetTuple(v any) []string {
	fields := map[string][]string{
		kindScenario:                  {fieldPlane, "scenario_family_id", "variation_point_id", fieldTargetID},
		kindParticipantImplementation: {fieldPlane, fieldParticipantAddress, "implementation_name", "implementation_version", "manifest_version", fieldTargetID},
		termApparatus:                 {fieldPlane, "component_kind", "component_name", "component_version", "manifest_version", fieldTargetID},
	}[stringAt(v, fieldPlane)]
	var result []string
	for _, field := range fields {
		result = append(result, stringAt(v, field))
	}
	return result
}
func bindingTargets(v any) error {
	ids, targets := []string{}, []string{}
	for _, descriptor := range array(v) {
		ids = append(ids, stringAt(descriptor, "binding_id"))
		target := targetTuple(at(descriptor, "target"))
		if target == nil {
			return invalid()
		}
		targets = append(targets, join(append([]string{stringAt(descriptor, "source_condition_id")}, target...)...))
	}
	return require(unique(ids) && unique(targets))
}
func selectionIdentity(i validation.Invocation) error {
	v := i.Instance
	target := targetTuple(at(v, "target"))
	if target == nil {
		return invalid()
	}
	actual, err := jsonDigest([]any{at(v, "source_condition_id"), at(v, "source_factor_id"), target})
	if err != nil {
		return err
	}
	return require(stringAt(v, "selection_id") == "selection-"+strings.TrimPrefix(actual, "sha256:"))
}
func studyRequired(i validation.Invocation) error {
	v := i.Instance
	kind := stringAt(v, "study_kind")
	if kind != kindStudy && kind != "benchmark" {
		return nil
	}
	return require(len(array(at(v, "research_questions"))) > 0 && len(array(at(v, "behavioral_claims"))) > 0 && at(v, "run_allocation") != nil && at(v, "analysis_plan") != nil && len(array(at(v, "validity_notes"))) > 0)
}
func adaptiveStudy(i validation.Invocation) error {
	v := i.Instance
	for _, assignment := range object(at(v, "run_allocation", "condition_assignments")) {
		condition := stringAt(assignment, "difficulty_condition")
		if condition != "" && condition != conditionFixed {
			return require(at(v, "analysis_plan") != nil && len(array(at(v, "validity_notes"))) > 0)
		}
	}
	return nil
}
func difficultyRegistry(i validation.Invocation) error {
	v := i.Instance
	registry := at(v, "difficulty_policy_registry")
	assignments := object(at(v, "allocation", "condition_assignments"))
	if registry == nil {
		return absentDifficultyRegistry(assignments)
	}
	if err := difficultyVariantRefs(registry, at(v, "selection_policies")); err != nil {
		return err
	}
	for _, assignment := range assignments {
		id := stringAt(assignment, "difficulty_policy_id")
		if id == "" {
			id = stringAt(registry, "default_policy_id")
		}
		policy := at(registry, "policies", id)
		condition := stringAt(assignment, "difficulty_condition")
		if condition == "" {
			condition = conditionFixed
		}
		if policy == nil || stringAt(policy, "condition") != condition {
			return invalid()
		}
	}
	return nil
}
func absentDifficultyRegistry(assignments map[string]any) error {
	for _, assignment := range assignments {
		if nonfixed(assignment) || at(assignment, "difficulty_policy_id") != nil {
			return invalid()
		}
	}
	return nil
}
func nonfixed(v any) bool {
	term := stringAt(v, "difficulty_condition")
	return term != "" && term != conditionFixed
}
func difficultyVariantRefs(registry, selections any) error {
	for _, variant := range object(at(registry, "variants")) {
		for _, id := range stringsOf(at(variant, "selection_policy_refs")) {
			if stringAt(object(selections)[id], termKind) != conditionFixed {
				return invalid()
			}
		}
	}
	return nil
}

// realizationMeaning removes design-axis labels before comparing criteria.
func realizationMeaning(v any, id string) map[string]any {
	meaning := maps.Clone(object(v))
	for _, field := range []string{id, "source_factor_id", "source_factor_level_id", "source_condition_id"} {
		delete(meaning, field)
	}
	return meaning
}

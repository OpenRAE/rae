package admission

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func allocationAssignments(i validation.Invocation) error {
	v := i.Instance
	assignments := at(v, "condition_assignments")
	if !fieldsUnique(v, "compared_conditions", "blocking_factors") || !sameKeys(assignments, set(at(v, "compared_conditions"))) || !keyed(assignments, "condition_id") {
		return invalid()
	}
	factors, criteria := []string{}, []string{}
	for _, assignment := range object(assignments) {
		if err := conditionSources(assignment); err != nil {
			return err
		}
		factor, err := sortedJSON(at(assignment, "factor_levels"))
		if err != nil {
			return err
		}
		criterion, err := conditionSignature(assignment)
		if err != nil {
			return err
		}
		factors = append(factors, factor)
		criteria = append(criteria, criterion)
	}
	return require(unique(factors) && unique(criteria))
}

func conditionSources(v any) error {
	if len(array(at(v, "required_refs")))+len(array(at(v, "required_parameters")))+len(array(at(v, termRequiredBindings)))+len(array(at(v, termRequiredSelections))) == 0 {
		return invalid()
	}
	if err := bindingTargets(at(v, termRequiredBindings)); err != nil {
		return err
	}
	if err := selectionSet(at(v, termRequiredSelections), at(v, termRequiredBindings)); err != nil {
		return err
	}
	for _, field := range []string{termRequiredBindings, termRequiredSelections} {
		for _, descriptor := range array(at(v, field)) {
			if !equal(at(descriptor, "source_condition_id"), at(v, "condition_id")) || !equal(at(descriptor, "source_factor_level_id"), at(v, "factor_levels", stringAt(descriptor, "source_factor_id"))) {
				return invalid()
			}
		}
	}
	return require(!nonfixed(v) || at(v, "difficulty_policy_id") != nil)
}
func selectionSet(selections, bindings any) error {
	if !unique(rowIDs(selections, "selection_id")) {
		return invalid()
	}
	points := []string{}
	for _, selection := range array(selections) {
		points = append(points, join(stringAt(selection, "target", "scenario_family_id"), stringAt(selection, "target", "variation_point_id")))
	}
	for _, binding := range array(bindings) {
		if stringAt(binding, "target", fieldPlane) == kindScenario {
			points = append(points, join(stringAt(binding, "target", "scenario_family_id"), stringAt(binding, "target", "variation_point_id")))
		}
	}
	return require(unique(points))
}
func sortedJSON(v any) (string, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return "", invalid()
	}
	canonical, err := canonjson.Sorted(raw, false)
	if err != nil {
		return "", invalid()
	}
	return string(canonical), nil
}
func conditionSignature(v any) (string, error) {
	refs, parameters := []string{}, []string{}
	for _, ref := range array(at(v, "required_refs")) {
		refs = append(refs, join(stringAt(ref, fieldRefKind), stringAt(ref, fieldRefID), stringAt(ref, fieldRefVersion), strings.ToLower(stringAt(ref, "ref_digest")), stringAt(ref, "ref_path")))
	}
	for _, parameter := range array(at(v, "required_parameters")) {
		value, err := sortedJSON(at(parameter, "value"))
		if err != nil {
			return "", err
		}
		parameters = append(parameters, join(stringAt(parameter, termName), stringAt(parameter, "value_kind"), value))
	}
	bindings, err := meaningKeys(at(v, termRequiredBindings), termBindingID)
	if err != nil {
		return "", err
	}
	selections, err := meaningKeys(at(v, termRequiredSelections), "selection_id")
	if err != nil {
		return "", err
	}
	slices.Sort(refs)
	slices.Sort(parameters)
	condition := stringAt(v, "difficulty_condition")
	if condition == "" {
		condition = conditionFixed
	}
	return sortedJSON([]any{refs, parameters, condition, at(v, "difficulty_policy_id"), bindings, selections})
}
func meaningKeys(rows any, id string) ([]string, error) {
	keys := make([]string, 0, len(array(rows)))
	for _, row := range array(rows) {
		key, err := sortedJSON(realizationMeaning(row, id))
		if err != nil {
			return nil, err
		}
		keys = append(keys, key)
	}
	slices.Sort(keys)
	return keys, nil
}

func bindingSources(i validation.Invocation) error {
	v := i.Instance
	typed := stringAt(v, "factorial_design", termProfile) == termFactorialTreatmentsV1
	descriptors := at(v, "binding_descriptors")
	explicit := stringAt(v, "binding_semantics") == termExplicitRequired
	if descriptors == nil {
		return require(!explicit || typed)
	}
	allocation := at(v, "run_plan", "allocation")
	if !explicit || allocation == nil {
		return invalid()
	}
	assignments := object(at(allocation, "condition_assignments"))
	covered := map[string]bool{}
	for id, assignment := range assignments {
		if len(array(at(assignment, "required_parameters"))) > 0 {
			return invalid()
		}
		if typed && len(array(at(assignment, termRequiredSelections))) > 0 {
			covered[id] = true
		}
	}
	for _, descriptor := range array(at(descriptors, "descriptors")) {
		condition, factor, level := stringAt(descriptor, "source_condition_id"), stringAt(descriptor, "source_factor_id"), stringAt(descriptor, "source_factor_level_id")
		if !set(at(v, "factors", factor, "levels"))[level] || stringAt(assignments[condition], "factor_levels", factor) != level {
			return invalid()
		}
		covered[condition] = true
	}
	return require(subset(stringsOf(at(allocation, "compared_conditions")), covered))
}

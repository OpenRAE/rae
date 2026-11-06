package admission

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) factorialRules() map[string]definition {
	return map[string]definition{"experiment-factorial-generation-valid": {check: func(i validation.Invocation) error { _, err := e.factorialExpand(i.Instance); return err }}}
}

func (e *Validator) prepare(id string, data []byte, limits ingress.Limits) ([]byte, error) {
	if id != termExperimentAuthoringInputV1 {
		return data, nil
	}
	if err := e.low.CheckSchema(id, data, limits); err != nil {
		return nil, err
	}
	value, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return nil, err
	}
	if at(value, "factorial_design") == nil {
		return data, nil
	}
	prepared, err := e.factorialExpand(value)
	if err != nil {
		return nil, err
	}
	raw, err := json.Marshal(prepared)
	if err != nil || len(raw) > 8*1048576 || len(raw) > limits.MaxBytes {
		return nil, invalid()
	}
	return raw, nil
}

func (e *Validator) factorialExpand(input any) (any, error) {
	if at(input, "factorial_design") == nil {
		return input, nil
	}
	v, err := e.defaulted(termExperimentAuthoringInputV1, input)
	if err != nil {
		return nil, err
	}
	design := at(v, "factorial_design")
	shape, err := factorialDimensions(v, design)
	if err != nil {
		return nil, err
	}
	if err = factorialWork(input, design, shape); err != nil {
		return nil, err
	}
	if at(v, "run_plan", "target_run_count") != nil {
		return nil, invalid()
	}
	semantics := stringAt(v, "binding_semantics")
	if semantics != "descriptive" && semantics != termExplicitRequired {
		return nil, invalid()
	}
	allocation, descriptors, err := factorialChildren(design, shape)
	if err != nil {
		return nil, err
	}
	if err = factorialSupplied(v, allocation, descriptors); err != nil {
		return nil, err
	}
	factorialAllocationDefaults(allocation)
	object(at(v, "run_plan"))["allocation"] = allocation
	object(v)["binding_descriptors"], object(v)["binding_semantics"] = descriptors, termExplicitRequired
	raw, err := json.Marshal(v)
	if err != nil || shape.typed && len(raw) > 8*1048576 {
		return nil, invalid()
	}
	return v, nil
}

type factorialShape struct {
	factors     []string
	levels      map[string][]string
	count, runs int
	typed       bool
	fixed       []any
}

func factorialDimensions(v, design any) (factorialShape, error) {
	shape := factorialShape{factors: stringsOf(at(design, "factor_ids")), levels: map[string][]string{}, count: 1, typed: stringAt(design, "profile") == termFactorialTreatmentsV1}
	section := "level_bindings"
	if shape.typed {
		section = "level_effects"
	}
	if !unique(shape.factors) || !sameKeys(at(design, section), set(at(design, "factor_ids"))) {
		return shape, invalid()
	}
	slices.Sort(shape.factors)
	object(design)["factor_ids"] = shape.factors
	bound, bok := integer(at(design, "condition_bound"))
	perCondition, rok := integer(at(design, "target_runs_per_condition"))
	if !bok || !rok {
		return shape, invalid()
	}
	for _, factor := range shape.factors {
		levels := stringsOf(at(v, "factors", factor, "levels"))
		if len(levels) == 0 || !unique(levels) || !sameKeys(at(design, section, factor), set(at(v, "factors", factor, "levels"))) || len(levels) > bound/shape.count {
			return shape, invalid()
		}
		slices.Sort(levels)
		shape.levels[factor] = levels
		shape.count *= len(levels)
	}
	if perCondition > 10000/shape.count {
		return shape, invalid()
	}
	shape.runs = perCondition * shape.count
	if shape.typed {
		var err error
		shape.fixed, err = factorialFixed(at(v, "run_plan", "selection_policies"))
		if err != nil {
			return shape, err
		}
	}
	return shape, nil
}

func factorialFixed(policies any) ([]any, error) {
	result := []any{}
	points := map[string]bool{}
	for _, policy := range object(policies) {
		point := stringAt(policy, "point_ref")
		if stringAt(policy, termKind) != conditionFixed || stringAt(policy, "purpose") != "fixed-configuration" || len(array(at(policy, "binding_descriptor_refs"))) > 0 || points[point] {
			return nil, invalid()
		}
		points[point] = true
		result = append(result, policy)
	}
	return result, nil
}

func factorialDescriptor(template any, factor, level, condition, idField, prefix string) (any, error) {
	descriptor := maps.Clone(object(template))
	digest, err := jsonDigest([]any{condition, factor, targetTuple(at(template, "target"))})
	if err != nil {
		return nil, err
	}
	descriptor[idField] = prefix + strings.TrimPrefix(digest, "sha256:")
	descriptor["source_factor_id"], descriptor["source_factor_level_id"], descriptor["source_condition_id"] = factor, level, condition
	return descriptor, nil
}

func factorialCondition(design any, shape factorialShape, levels map[string]any) (any, error) {
	digest, err := jsonDigest(levels)
	if err != nil {
		return nil, err
	}
	id := "condition-" + strings.TrimPrefix(digest, "sha256:")[:48]
	bindings, selections := []any{}, []any{}
	for _, factor := range shape.factors {
		level := text(levels[factor])
		templates := at(design, "level_bindings", factor, level)
		if shape.typed {
			templates = at(design, "level_effects", factor, level, termBindings)
		}
		for _, template := range array(templates) {
			descriptor, err := factorialDescriptor(template, factor, level, id, "binding_id", "binding-")
			if err != nil {
				return nil, err
			}
			bindings = append(bindings, descriptor)
		}
		for _, template := range array(at(design, "level_effects", factor, level, "selections")) {
			descriptor, err := factorialDescriptor(template, factor, level, id, "selection_id", "selection-")
			if err != nil {
				return nil, err
			}
			selections = append(selections, descriptor)
		}
	}
	slices.SortFunc(bindings, func(a, b any) int { return strings.Compare(stringAt(a, "binding_id"), stringAt(b, "binding_id")) })
	slices.SortFunc(selections, func(a, b any) int { return strings.Compare(stringAt(a, "selection_id"), stringAt(b, "selection_id")) })
	return map[string]any{"condition_id": id, "factor_levels": maps.Clone(levels), "difficulty_condition": conditionFixed, "difficulty_policy_id": nil, "required_refs": []any{}, "required_parameters": []any{}, termRequiredBindings: bindings, termRequiredSelections: selections, "description": nil}, nil
}

func factorialChildren(design any, shape factorialShape) (any, any, error) {
	assignments := map[string]any{}
	descriptors := []any{}
	indices := make([]int, len(shape.factors))
	var points map[string]bool
	for range shape.count {
		levels := map[string]any{}
		for index, factor := range shape.factors {
			levels[factor] = shape.levels[factor][indices[index]]
		}
		condition, err := factorialCondition(design, shape, levels)
		if err != nil {
			return nil, nil, err
		}
		id := stringAt(condition, "condition_id")
		if assignments[id] != nil {
			return nil, nil, invalid()
		}
		if err := conditionSources(condition); err != nil {
			return nil, nil, err
		}
		if shape.typed {
			current, err := factorialConsistentPoints(condition, shape.fixed, points)
			if err != nil {
				return nil, nil, err
			}
			points = current
		}
		assignments[id] = condition
		descriptors = append(descriptors, array(at(condition, termRequiredBindings))...)
		factorialNext(indices, shape)
	}
	conditions := mapKeys(assignments)
	slices.Sort(conditions)
	slices.SortFunc(descriptors, func(a, b any) int { return strings.Compare(stringAt(a, "binding_id"), stringAt(b, "binding_id")) })
	allocation := map[string]any{"allocation_unit": kindRun, "allocation_method": at(design, "profile"), "compared_conditions": conditions, "condition_assignments": assignments, "target_runs_per_condition": at(design, "target_runs_per_condition"), "randomization_unit": nil, "blocking_factors": []any{}, "replication_policy": "equal independent runs", "stopping_rule": nil}
	if len(descriptors) == 0 {
		return allocation, nil, nil
	}
	return allocation, map[string]any{termSchemaVersion: "experiment-binding-descriptors/v1", "descriptors": descriptors}, nil
}

func factorialNext(indices []int, shape factorialShape) {
	for index := len(indices) - 1; index >= 0; index-- {
		indices[index]++
		if indices[index] < len(shape.levels[shape.factors[index]]) {
			return
		}
		indices[index] = 0
	}
}

func factorialPoints(condition any, fixed []any) (map[string]bool, error) {
	points := []string{}
	for _, policy := range fixed {
		points = append(points, stringAt(policy, "point_ref"))
	}
	for _, binding := range array(at(condition, termRequiredBindings)) {
		if stringAt(binding, "target", "plane") == kindScenario {
			points = append(points, stringAt(binding, "target", "variation_point_id"))
		}
	}
	for _, selection := range array(at(condition, termRequiredSelections)) {
		points = append(points, stringAt(selection, "target", "variation_point_id"))
	}
	if !unique(points) {
		return nil, invalid()
	}
	result := map[string]bool{}
	for _, point := range points {
		result[point] = true
	}
	return result, nil
}

func factorialConsistentPoints(condition any, fixed []any, previous map[string]bool) (map[string]bool, error) {
	current, err := factorialPoints(condition, fixed)
	if err != nil {
		return nil, err
	}
	if previous != nil && !equalSet(current, previous) {
		return nil, invalid()
	}
	return current, nil
}

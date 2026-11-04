package admission

import (
	"math/big"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) selectionRules() map[string]definition {
	return map[string]definition{
		"experiment-selection-policies-valid":     {check: e.selectionRegistry},
		"experiment-selection-factor-joins-valid": {check: selectionFactors},
		"stochastic-draws-control-ref-resolves":   {check: e.stochasticDraws},
	}
}
func (e *Validator) selectionRegistry(i validation.Invocation) error {
	v := i.Instance
	if plan := at(v, "run_plan"); plan != nil {
		v = plan
	}
	policies := at(v, "selection_policies")
	if !keyed(policies, "policy_id") || !unique(rowIDs(at(v, "stochastic_controls"), "control_id")) {
		return invalid()
	}
	total, ok := number(at(v, "target_run_count"))
	if allocation := at(v, "allocation"); allocation != nil {
		perCondition, valid := number(at(allocation, "target_runs_per_condition"))
		if !valid {
			return invalid()
		}
		total = new(big.Rat).Mul(perCondition, big.NewRat(int64(len(array(at(allocation, "compared_conditions")))), 1))
		ok = true
	}
	if !ok {
		return invalid()
	}
	products := map[string][]string{}
	for id, policy := range object(policies) {
		if err := e.selectionPolicy(v, policy, total); err != nil {
			return err
		}
		if stringAt(policy, termKind) == "product" {
			if err := productPolicy(policy, policies); err != nil {
				return err
			}
			products[id] = stringsOf(at(policy, "policy_refs"))
		}
	}
	return require(!graph.HasCycle(products))
}
func (e *Validator) selectionPolicy(plan, policy any, total *big.Rat) error {
	bound, ok := number(at(policy, "output_bound"))
	if !ok || bound.Cmp(total) > 0 {
		return invalid()
	}
	if !fieldsUnique(policy, "binding_descriptor_refs", "policy_refs") {
		return invalid()
	}
	switch stringAt(policy, termKind) {
	case conditionFixed:
		return require(bound.Cmp(big.NewRat(1, 1)) == 0)
	case "sample":
		if !numericEqual(at(policy, "sample_count"), at(policy, "output_bound")) || bound.Cmp(total) != 0 {
			return invalid()
		}
		return e.sampleControl(plan, policy)
	case termStratified:
		return stratifiedPolicy(policy)
	case "enumerate", "product":
		return nil
	default:
		return invalid()
	}
}
func (e *Validator) sampleControl(plan, policy any) error {
	for _, control := range array(at(plan, "stochastic_controls")) {
		if stringAt(control, "control_id") != stringAt(policy, "stochastic_control_ref") {
			continue
		}
		role := stringAt(control, "role")
		if role != "sampling" && role != "randomization" {
			return invalid()
		}
		return require(stringAt(e.streams[stringAt(control, "executable_binding", "profile_ref", fieldRefID)], "transforms", "bounded-integer", "version") == "1")
	}
	return invalid()
}
func productPolicy(policy, policies any) error {
	product := big.NewRat(1, 1)
	controlled := false
	for _, ref := range stringsOf(at(policy, "policy_refs")) {
		child := object(policies)[ref]
		bound, ok := number(at(child, "output_bound"))
		if !ok {
			return invalid()
		}
		product.Mul(product, bound)
		if product.Cmp(big.NewRat(1000000, 1)) > 0 {
			return invalid()
		}
		controlled = controlled || stringAt(child, "purpose") == "controlled-factor"
	}
	bound, ok := number(at(policy, "output_bound"))
	return require(ok && bound.Cmp(product) == 0 && controlled == (stringAt(policy, "purpose") == "controlled-factor"))
}
func stratifiedPolicy(policy any) error {
	strata := at(policy, "strata")
	if !keyed(strata, "stratum_id") || !keyed(strata, "condition_id") {
		return invalid()
	}
	sum := big.NewRat(0, 1)
	var first *big.Rat
	for _, stratum := range object(strata) {
		if at(policy, "outcomes", stringAt(stratum, "outcome_ref")) == nil {
			return invalid()
		}
		count, ok := number(at(stratum, "output_count"))
		if !ok {
			return invalid()
		}
		if first != nil && first.Cmp(count) != 0 {
			return invalid()
		}
		first = count
		sum.Add(sum, count)
	}
	bound, ok := number(at(policy, "output_bound"))
	return require(ok && bound.Cmp(sum) == 0)
}
func selectionFactors(i validation.Invocation) error {
	v := i.Instance
	descriptors := map[string]any{}
	for _, descriptor := range array(at(v, "binding_descriptors", "descriptors")) {
		descriptors[stringAt(descriptor, "binding_id")] = descriptor
	}
	allocation := at(v, "run_plan", "allocation")
	for _, policy := range object(at(v, "run_plan", "selection_policies")) {
		if err := selectionBindingRefs(policy, descriptors); err != nil {
			return err
		}
		if stringAt(policy, termKind) == termStratified {
			if allocation == nil || !sameKeys(at(policy, "strata"), set(at(allocation, "compared_conditions"))) {
				return invalid()
			}
			if err := stratumFactors(v, policy, allocation); err != nil {
				return err
			}
		}
	}
	return nil
}
func selectionBindingRefs(policy any, descriptors map[string]any) error {
	for _, ref := range stringsOf(at(policy, "binding_descriptor_refs")) {
		if descriptors[ref] == nil || !equal(at(descriptors[ref], "target", "variation_point_id"), at(policy, "point_ref")) {
			return invalid()
		}
	}
	return nil
}
func stratumFactors(spec, policy, allocation any) error {
	for _, stratum := range object(at(policy, "strata")) {
		factor, level, condition := stringAt(stratum, "factor_id"), stringAt(stratum, "factor_level_id"), stringAt(stratum, "condition_id")
		if !set(at(spec, "factors", factor, "levels"))[level] || stringAt(allocation, "condition_assignments", condition, "factor_levels", factor) != level || !numericEqual(at(stratum, "output_count"), at(allocation, "target_runs_per_condition")) {
			return invalid()
		}
	}
	return nil
}
func (e *Validator) stochasticDraws(i validation.Invocation) error {
	controls := map[string]any{}
	for _, control := range array(at(i.Instance, "stochastic_controls")) {
		controls[stringAt(control, "control_id")] = control
	}
	for _, draw := range array(at(i.Instance, "stochastic_draws")) {
		binding := at(controls[stringAt(draw, "control_id")], "executable_binding")
		if binding == nil || !equal(at(draw, "address", "namespace"), at(binding, "namespace")) {
			return invalid()
		}
		profile := e.streams[stringAt(binding, "profile_ref", fieldRefID)]
		if profile == nil || !equal(at(profile, "transforms", stringAt(draw, "transform_id"), "version"), at(draw, "transform_version")) {
			return invalid()
		}
	}
	return nil
}

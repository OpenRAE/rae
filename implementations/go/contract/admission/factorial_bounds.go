package admission

import (
	"encoding/json"
	"maps"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
)

func factorialWork(input, design any, shape factorialShape) error {
	work := 0
	for _, policy := range shape.fixed {
		work += 1 + len(array(at(policy, "outcome", "member_ids")))
	}
	for _, factor := range shape.factors {
		maximum, err := factorialFactorWork(design, shape, factor)
		if err != nil {
			return err
		}
		work += maximum
	}
	units := shape.count
	if shape.typed {
		units = shape.runs
	}
	if work > 10000/units {
		return invalid()
	}
	if shape.typed {
		return factorialByteBound(input, design, shape)
	}
	return nil
}

func factorialByteBound(input, design any, shape factorialShape) error {
	// Normalize only the design model here. The reference reserves bytes using
	// the original source carrier, before the full authoring model is built.
	factorialEffectDefaults(design)
	compact := maps.Clone(object(input))
	compact["factorial_design"] = design
	delete(compact, "binding_descriptors")
	plan := maps.Clone(object(at(input, "run_plan")))
	delete(plan, "allocation")
	compact["run_plan"] = plan
	sourceBytes, err := factorialCanonicalLen(compact)
	if err != nil {
		return err
	}
	conditionBytes := 512
	for _, factor := range shape.factors {
		maximum := 0
		for _, level := range shape.levels[factor] {
			effects := at(design, "level_effects", factor, level)
			encoded, err := factorialCanonicalLen(effects)
			if err != nil {
				return err
			}
			labels, err := factorialCanonicalLen([]string{factor, level})
			if err != nil {
				return err
			}
			count := len(array(at(effects, termBindings))) + len(array(at(effects, "selections")))
			maximum = max(maximum, encoded+count*(512+labels))
		}
		conditionBytes += maximum
	}
	return require(sourceBytes+2*shape.count*conditionBytes <= 8*1048576)
}

func factorialCanonicalLen(v any) (int, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return 0, invalid()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return 0, invalid()
	}
	return len(canonical), nil
}

func factorialSupplied(v, allocation, descriptors any) error {
	supplied := at(v, "run_plan", "allocation")
	if supplied != nil {
		factorialAllocationDefaults(supplied)
		factorialAllocationDefaults(allocation)
		if !equal(supplied, allocation) {
			return invalid()
		}
	}
	if at(v, "binding_descriptors") != nil && !equal(at(v, "binding_descriptors"), descriptors) {
		return invalid()
	}
	return nil
}

func factorialAllocationDefaults(allocation any) {
	if at(allocation, "blocking_factors") == nil {
		object(allocation)["blocking_factors"] = []any{}
	}
	for _, assignment := range object(at(allocation, "condition_assignments")) {
		for _, field := range []string{"required_refs", "required_parameters"} {
			if at(assignment, field) == nil {
				object(assignment)[field] = []any{}
			}
		}
		for _, field := range []string{termRequiredBindings, termRequiredSelections} {
			if len(array(at(assignment, field))) == 0 {
				delete(object(assignment), field)
			}
		}
	}
}

func factorialFactorWork(design any, shape factorialShape, factor string) (int, error) {
	maximum := 0
	for _, level := range shape.levels[factor] {
		cost := len(array(at(design, "level_bindings", factor, level)))
		if shape.typed {
			effects := at(design, "level_effects", factor, level)
			cost = len(array(at(effects, termBindings)))
			count := cost + len(array(at(effects, "selections")))
			if count < 1 || count > 16 {
				return 0, invalid()
			}
			for _, selection := range array(at(effects, "selections")) {
				cost += 1 + len(array(at(selection, "outcome", "member_ids")))
			}
		}
		maximum = max(maximum, cost)
	}
	return maximum, nil
}

func factorialEffectDefaults(design any) {
	for _, levels := range object(at(design, "level_effects")) {
		for _, effects := range object(levels) {
			for _, field := range []string{termBindings, "selections"} {
				if at(effects, field) == nil {
					object(effects)[field] = []any{}
				}
			}
		}
	}
}

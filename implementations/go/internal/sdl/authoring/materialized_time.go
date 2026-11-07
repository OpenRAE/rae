package authoring

import (
	"encoding/json"
	"math/big"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func (c materializedChecks) timeModel() error {
	domains := object(c.value["time_domains"])
	for _, raw := range object(c.value["clocks"]) {
		if _, present := domains[text(object(raw)["time_domain_ref"])]; !present {
			return semanticInvalid()
		}
	}
	if err := c.timeMappings(domains); err != nil {
		return err
	}
	if err := c.timePolicies(); err != nil {
		return err
	}
	return c.timeConstraints()
}
func (c materializedChecks) timeMappings(domains map[string]any) error {
	edges := map[string][]string{}
	pairs := map[[2]string]bool{}
	for _, raw := range object(c.value["time_domain_mappings"]) {
		mapping := object(raw)
		source, target := text(mapping["source_domain_ref"]), text(mapping["target_domain_ref"])
		left, right := object(domains[source]), object(domains[target])
		pair := [2]string{source, target}
		if left == nil || right == nil || pairs[pair] {
			return semanticInvalid()
		}
		pairs[pair] = true
		if mapping["mapping_kind"] == "identity" && (left["epoch"] != right["epoch"] || !sameRatio(object(left["tick_period_seconds"]), object(right["tick_period_seconds"]))) {
			return semanticInvalid()
		}
		edges[source] = append(edges[source], target)
	}
	if graph.HasCycle(edges) {
		return semanticInvalid()
	}
	return nil
}
func sameRatio(left, right map[string]any) bool {
	for _, field := range []string{"numerator", "denominator"} {
		a, aok := modelInteger(left[field])
		b, bok := modelInteger(right[field])
		if !aok || !bok || a.Cmp(b) != 0 {
			return false
		}
	}
	return true
}
func modelInteger(value any) (*big.Int, bool) {
	number, ok := value.(json.Number)
	if !ok {
		return nil, false
	}
	// Model ingress already bounds the coefficient/exponent and schema type.
	rational, ok := new(big.Rat).SetString(string(number))
	if !ok || !rational.IsInt() {
		return nil, false
	}
	return rational.Num(), true
}
func (c materializedChecks) timePolicies() error {
	clocks := object(c.value["clocks"])
	owners := map[string]bool{}
	for _, raw := range object(c.value["time_progression_policies"]) {
		policy := object(raw)
		reference := text(policy["clock_ref"])
		clock := object(clocks[reference])
		if clock == nil || owners[reference] {
			return semanticInvalid()
		}
		owners[reference] = true
		if (policy["reset_behavior"] != "unsupported" || policy["replay_behavior"] != "unsupported") && clock["supports_reset"] != true {
			return semanticInvalid()
		}
	}
	return nil
}
func (c materializedChecks) timeConstraints() error {
	clocks := object(c.value["clocks"])
	steps := c.workflowStepNames()
	for _, raw := range object(c.value["temporal_constraints"]) {
		constraint := object(raw)
		if _, present := clocks[text(constraint["clock_ref"])]; !present {
			return semanticInvalid()
		}
		for _, rawRef := range array(constraint["subject_refs"]) {
			reference := text(rawRef)
			if steps[reference] {
				continue
			}
			if !c.index.uniqueDeclared(reference) {
				return semanticInvalid()
			}
		}
	}
	return nil
}

func (c materializedChecks) workflowStepNames() map[string]bool {
	steps := map[string]bool{}
	for name, raw := range object(c.value[workflowsSection]) {
		for step := range object(object(raw)["steps"]) {
			steps[name+"."+step] = true
		}
	}
	return steps
}

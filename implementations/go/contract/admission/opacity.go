package admission

import (
	"encoding/json"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) opacityRules() map[string]definition {
	return map[string]definition{
		"participant-opacity-finite-carrier-counts":      {check: opacityCarrier},
		"participant-opacity-model-check-graph-joins":    {check: opacityGraph},
		"participant-opacity-evidence-joins":             {check: e.opacityEvidence},
		"participant-opacity-model-check-evidence-joins": {check: e.opacityModelEvidence},
	}
}

func integer(v any) (int, bool) {
	r, ok := number(v)
	if !ok || !r.IsInt() || !r.Num().IsInt64() {
		return 0, false
	}
	n := r.Num().Int64()
	return int(n), int64(int(n)) == n
}
func countEqual(v any, n int) bool      { return numericEqual(v, json.Number(strconv.Itoa(n))) }
func countAt(v any, path ...string) int { n, _ := integer(at(v, path...)); return n }
func rowTupleSet(rows any, fields ...string) map[string]bool {
	result := map[string]bool{}
	for _, row := range array(rows) {
		values := make([]string, len(fields))
		for j, field := range fields {
			values[j] = stringAt(row, field)
		}
		result[join(values...)] = true
	}
	return result
}
func opacityCounts(rows any) map[string]int {
	result := map[string]int{}
	for field, column := range map[string]string{"runs": "run_ref", "cuts": "cut_ref", "strategies": fieldStrategyRef, "order_variants": "order_ref"} {
		result[field] = len(rowSet(rows, column))
	}
	result["scheduler_environment_pairs"] = len(rowTupleSet(rows, "scheduler_ref", "environment_ref"))
	return result
}
func exactCounts(counts any, expected map[string]int) error {
	if len(object(counts)) != len(expected) {
		return invalid()
	}
	for key, n := range expected {
		if !countEqual(at(counts, key), n) {
			return invalid()
		}
	}
	return nil
}
func opacityCarrier(i validation.Invocation) error {
	rows := at(i.Instance, "points")
	if len(rowSet(rows, "point_ref")) != len(array(rows)) {
		return invalid()
	}
	seen := make([]bool, len(array(rows)))
	for _, point := range array(rows) {
		n, ok := integer(at(point, "ordinal"))
		if !ok || n < 0 || n >= len(seen) || seen[n] {
			return invalid()
		}
		seen[n] = true
	}
	counts := opacityCounts(rows)
	counts["points"] = len(array(rows))
	return exactCounts(at(i.Instance, "declared_counts"), counts)
}
func opacityAssumptions(v any) error {
	for _, field := range []string{"strategy_refs", "scheduler_refs", "environment_refs", "order_refs"} {
		if !sortedUnique(stringsOf(at(v, field))) {
			return invalid()
		}
	}
	return nil
}
func opacityClaimScope(claim, assumptions any, model bool) error {
	axis, status, evidence, quantifier, kind := "bounded-test", statusTested, "finite", "finite-cases", "input"
	if model {
		axis, status, evidence, quantifier, kind = "model-check", "model-checked", "model-check", "all-traces", "model"
		if stringAt(assumptions, "strategy_kind") == termActive {
			quantifier = "all-strategies"
		}
	}
	if stringAt(claim, "assurance_axis") != axis || stringAt(claim, "assurance_status") != status || stringAt(claim, "evidence_scope") != evidence || stringAt(claim, "quantifier_scope") != quantifier {
		return invalid()
	}
	return require(set(at(claim, "explicit_non_claims"))["No source or materializer authenticity is established by this normalized-"+kind+" evidence."])
}

func opacityGraph(i validation.Invocation) error {
	v := i.Instance
	states, transitions := array(at(v, "states")), array(at(v, termTransitions))
	if err := opacityGraphIdentities(v); err != nil {
		return err
	}
	counts := opacityCounts(states)
	counts["states"], counts[termTransitions], counts["initial_states"] = len(states), len(transitions), len(array(at(v, "initial_state_ordinals")))
	for _, state := range states {
		if boolean(at(state, "evaluation_point")) {
			counts["evaluation_points"]++
		}
	}
	if _, ok := counts["evaluation_points"]; !ok {
		counts["evaluation_points"] = 0
	}
	if err := exactCounts(at(v, "declared_counts"), counts); err != nil {
		return err
	}
	if err := opacityGraphDomains(v); err != nil {
		return err
	}
	return opacityClaimScope(at(v, "claim"), at(v, fieldAssumptions), true)
}

func opacityGraphDomains(v any) error {
	assumptions := at(v, fieldAssumptions)
	if err := opacityAssumptions(assumptions); err != nil {
		return err
	}
	states := array(at(v, "states"))
	for _, prefix := range []string{"strategy", "scheduler", "environment", termOrder} {
		if !equalSet(rowSet(states, prefix+"_ref"), set(at(assumptions, prefix+"_refs"))) {
			return invalid()
		}
	}
	if !equalSet(rowSet(states, "cut_ref"), map[string]bool{stringAt(assumptions, "cut_ref"): true}) {
		return invalid()
	}
	pairs := rowTupleSet(states, "scheduler_ref", "environment_ref")
	if len(pairs) != len(array(at(assumptions, "scheduler_refs")))*len(array(at(assumptions, "environment_refs"))) {
		return invalid()
	}
	initial := make([]any, 0, len(array(at(v, "initial_state_ordinals"))))
	previous := -1
	for _, value := range array(at(v, "initial_state_ordinals")) {
		n, ok := integer(value)
		if !ok || n <= previous || n >= len(states) {
			return invalid()
		}
		previous = n
		initial = append(initial, states[n])
	}
	actual := rowTupleSet(initial, fieldStrategyRef, "scheduler_ref", "environment_ref", "order_ref")
	expected := len(array(at(assumptions, "strategy_refs"))) * len(pairs) * len(array(at(assumptions, "order_refs")))
	return require(len(actual) == expected)
}

func opacityGraphIdentities(v any) error {
	states, transitions := array(at(v, "states")), array(at(v, termTransitions))
	for field, ref := range map[string]string{"states": "state_ref", termTransitions: termTransitionRef} {
		rows := array(at(v, field))
		if len(rowSet(rows, ref)) != len(rows) {
			return invalid()
		}
		for j, row := range rows {
			if !countEqual(at(row, "ordinal"), j) {
				return invalid()
			}
		}
	}
	return opacityGraphEdges(states, transitions)
}

func opacityGraphEdges(states, transitions []any) error {
	for _, edge := range transitions {
		source, sok := integer(at(edge, "source_state_ordinal"))
		target, tok := integer(at(edge, "target_state_ordinal"))
		if !sok || !tok || source < 0 || target < 0 || source >= len(states) || target >= len(states) {
			return invalid()
		}
		for _, field := range []string{fieldStrategyRef, "scheduler_ref", "environment_ref", "order_ref"} {
			if !equal(at(states[source], field), at(states[target], field)) {
				return invalid()
			}
		}
	}
	return nil
}

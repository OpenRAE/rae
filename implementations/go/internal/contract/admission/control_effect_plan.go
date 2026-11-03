package admission

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func controlEffectPlan(v any) error {
	effects, decisions, outcomes := array(at(v, termEffects)), array(at(v, "decisions")), array(at(v, "effect_outcomes"))
	if stringAt(v, "parent_crossing", termKind) != "crossing" || len(rowSet(outcomes, "effect_id")) != len(outcomes) || !subsetSet(rowSet(outcomes, "effect_id"), rowSet(effects, "effect_id")) {
		return invalid()
	}
	applied := map[string]bool{}
	for _, outcome := range outcomes {
		if stringAt(outcome, "disposition") == termApplied {
			applied[stringAt(outcome, "effect_id")] = true
		}
	}
	if !equalSet(applied, set(at(v, "realized_effect_ids"))) || !fieldsUnique(v, "realized_effect_ids") || len(rowSet(effects, "effect_id")) != len(effects) || len(rowSet(decisions, termDecisionID)) != len(decisions) || !uniqueValues(controlEffectKeys(effects)) {
		return invalid()
	}
	if err := controlParentReceipts(v); err != nil {
		return err
	}
	if err := controlParentEffectGraph(v, effects); err != nil {
		return err
	}
	return controlPlanDerived(v, effects, decisions, applied)
}

func controlEffectKeys(effects []any) []any {
	keys := make([]any, len(effects))
	for index, effect := range effects {
		keys[index] = at(effect, "key")
	}
	return keys
}

func controlParentReceipts(v any) error {
	admission, application := at(v, "parent_admission_receipt"), at(v, "parent_application_receipt")
	if boolean(at(v, "parent_applied")) && (admission == nil || application == nil) || !boolean(at(v, "parent_applied")) && application != nil {
		return invalid()
	}
	for _, receipt := range []any{admission, application} {
		if receipt != nil && stringAt(receipt, termKind) != termReceipt {
			return invalid()
		}
	}
	return nil
}

func controlParentEffectGraph(v any, effects []any) error {
	realized := set(at(v, "realized_effect_ids"))
	if !subsetSet(realized, rowSet(effects, "effect_id")) {
		return invalid()
	}
	edges := map[string][]string{"@parent-admitted": {}, "@parent-applied": {"@parent-admitted"}}
	for _, effect := range effects {
		id := stringAt(effect, "effect_id")
		edges[id] = stringsOf(at(effect, "predecessor_effect_ids"))
		if realized[id] && !subset(stringsOf(at(effect, "predecessor_effect_ids")), realized) {
			return invalid()
		}
		if stringAt(effect, "phase") == termRequiredPredecessor {
			edges["@parent-admitted"] = append(edges["@parent-admitted"], id)
		}
		if stringAt(effect, "phase") == termSuccessDependent {
			edges[id] = append(edges[id], "@parent-"+stringAt(effect, "parent_outcome"))
		}
	}
	if graph.HasCycle(edges) {
		return invalid()
	}
	if _, err := graph.Order(edges, nil); err != nil {
		return invalid()
	}
	return controlEffectConflicts(effects)
}

func controlBaseParent(decisions []any, gate string) string {
	dispositions := rowSet(decisions, "disposition")
	if dispositions[termDeny] || gate == termDeny {
		return termDeny
	}
	if dispositions[termWithhold] || gate != termPermit {
		return termWithhold
	}
	return termPermit
}

func controlEffectRunnable(plan, effect any, realized map[string]bool, base, final string, ready bool) bool {
	if realized[stringAt(effect, "effect_id")] || !subset(stringsOf(at(effect, "predecessor_effect_ids")), realized) {
		return false
	}
	switch stringAt(effect, "phase") {
	case termRequiredPredecessor:
		return base == termPermit
	case termSuccessDependent:
		return base == termPermit && ready && (stringAt(effect, "parent_outcome") == "admitted" && at(plan, "parent_admission_receipt") != nil || stringAt(effect, "parent_outcome") == termApplied && boolean(at(plan, "parent_applied")))
	case termIndependent:
		return set(at(effect, "allowed_parent_dispositions"))[final]
	default:
		return false
	}
}

func controlPlanDerived(v any, effects, decisions []any, applied map[string]bool) error {
	base := controlBaseParent(decisions, stringAt(v, "incumbent_gate_disposition"))
	pending := map[string]bool{}
	for _, effect := range effects {
		if stringAt(effect, "phase") == termRequiredPredecessor && !applied[stringAt(effect, "effect_id")] {
			pending[stringAt(effect, "effect_id")] = true
		}
	}
	final := base
	if base == termPermit && len(pending) > 0 {
		final = termWithhold
	}
	runnable := []string{}
	for _, effect := range effects {
		if controlEffectRunnable(v, effect, applied, base, final, len(pending) == 0) {
			runnable = append(runnable, stringAt(effect, "effect_id"))
		}
	}
	slices.Sort(runnable)
	return require(stringAt(v, "parent_disposition") == final && equal(stringsOf(at(v, "runnable_effect_ids")), runnable))
}

func controlEffectConflicts(effects []any) error {
	for index, left := range effects {
		for _, right := range effects[index+1:] {
			a, b := at(left, "target"), at(right, "target")
			if controlEffectSubject(a) == controlEffectSubject(b) && controlSameSubjectConflict(a, b) {
				return invalid()
			}
		}
	}
	return nil
}

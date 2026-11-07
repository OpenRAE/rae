package authoring

import (
	"encoding/json"
	"maps"
)

func (d injectDelivery) control() error {
	if d.binding["delivery_kind"] == "disclosure" {
		return nil
	}
	policy := object(d.spec["mixed_control"])
	control := object(d.binding[controlTerm])
	reusable := policy["semantics"] == "mixed-control-policy-occurrence/rev1"
	if control != nil || reusable {
		if control == nil || !reusable {
			return semanticInvalid()
		}
		return d.reusableControl(policy, control)
	}
	transition := object(object(policy["transitions"])[text(d.binding["control_transition_ref"])])
	if policy == nil || transition == nil {
		return semanticInvalid()
	}
	state := object(object(policy["controller_states"])[text(transition["to_state_ref"])])
	if err := d.legacyControl(policy, transition, state); err != nil {
		return err
	}
	if err := d.controlTime(); err != nil {
		return err
	}
	return d.controlEvidence(array(d.binding["control_evidence_refs"]), array(transition[evidenceRefsField]), array(state[evidenceRefsField]), true)
}
func (d injectDelivery) reusableControl(policy, control map[string]any) error {
	if control["semantics"] != policy["semantics"] || control["policy_revision"] != policy["policy_revision"] || policy["participant_ref"] != d.binding["participant_ref"] {
		return semanticInvalid()
	}
	transition := object(object(policy["permitted_transitions"])[text(control["permitted_transition_ref"])])
	if transition == nil || transition["transition_kind"] != d.binding["delivery_kind"] {
		return semanticInvalid()
	}
	state := object(object(policy["controller_states"])[text(transition["from_state_ref"])])
	if deliveryController(d.binding, control) != resolvedController(policy, state) {
		return semanticInvalid()
	}
	actual, err := d.root.index.canonicalRefs(array(control[authorityScopeRefsField]), "scope")
	if err != nil || len(actual) == 0 {
		return semanticInvalid()
	}
	if err = d.root.controlRefsWithin(array(control[authorityScopeRefsField]), array(state[scopeRefsField]), d.root.index, "scope"); err != nil {
		return err
	}
	return d.controlEvidence(array(control[evidenceRefsField]), array(transition[evidenceRefsField]), array(state[evidenceRefsField]), false)
}
func deliveryController(binding, control map[string]any) string {
	controller := text(control["controller_ref"])
	if controller == "self" {
		return text(binding["participant_ref"])
	}
	return controller
}
func (d injectDelivery) legacyControl(policy, transition, state map[string]any) error {
	if transition["transition_kind"] != d.binding["delivery_kind"] || policy["participant_ref"] != d.binding["participant_ref"] || policy["policy_revision"] != object(d.binding["delivery_policy"])["policy_revision"] || deliveryController(d.binding, d.binding) != resolvedController(policy, state) {
		return semanticInvalid()
	}
	for _, field := range []string{"effective_order", "valid_from_order", "valid_until_order"} {
		if !modelNumberEqual(d.binding["control_"+field], transition[field]) {
			return semanticInvalid()
		}
	}
	if !mixedWindowContains(state, d.binding["control_effective_order"]) {
		return semanticInvalid()
	}
	actual, err := d.root.index.canonicalRefs(array(d.binding["control_authority_scope_refs"]), "scope")
	if err != nil {
		return err
	}
	expected, err := d.root.index.canonicalRefs(array(state[scopeRefsField]), "scope")
	if err != nil || !maps.Equal(actual, expected) {
		return semanticInvalid()
	}
	return nil
}
func (d injectDelivery) controlEvidence(refs, transition, state []any, exact bool) error {
	actual, err := d.root.index.canonicalRefs(refs, "target")
	if err != nil || len(actual) == 0 {
		return semanticInvalid()
	}
	transitionRefs, err := d.root.index.canonicalRefs(transition, "declared")
	if err != nil {
		return err
	}
	stateRefs, err := d.root.index.canonicalRefs(state, "declared")
	if err != nil {
		return err
	}
	if exact && (!maps.Equal(actual, transitionRefs) || !maps.Equal(actual, stateRefs)) {
		return semanticInvalid()
	}
	maps.Copy(transitionRefs, stateRefs)
	if !refsWithin(actual, transitionRefs) {
		return semanticInvalid()
	}
	covered := map[string]bool{}
	for _, ref := range array(d.binding[evidenceRequirementRefsField]) {
		requirement := object(object(d.root.value["evidence_requirements"])[text(ref)])
		resolved, err := d.root.index.canonicalRefs(array(requirement[scopeRefsField]), "declared")
		if err != nil {
			return err
		}
		maps.Copy(covered, resolved)
	}
	if !refsWithin(actual, covered) {
		return semanticInvalid()
	}
	return nil
}
func (d injectDelivery) controlTime() error {
	coordinate := map[string]any{"tick": d.binding["control_effective_order"]}
	bounded := false
	for _, ref := range array(d.binding["temporal_constraint_refs"]) {
		constraint := object(object(d.root.value["temporal_constraints"])[text(ref)])
		start, end := object(constraint["start"]), object(constraint["end"])
		if start != nil {
			bounded = true
			if coordinateLess(coordinate, start) {
				return semanticInvalid()
			}
		}
		if end != nil {
			bounded = true
			if coordinateLess(end, coordinate) {
				return semanticInvalid()
			}
		}
	}
	if !bounded {
		return semanticInvalid()
	}
	return nil
}

func coordinateLess(left, right map[string]any) bool {
	for _, field := range []string{"tick", "microstep"} {
		a, b := left[field], right[field]
		if a == nil {
			a = json.Number("0")
		}
		if b == nil {
			b = json.Number("0")
		}
		if modelLess(a, b) {
			return true
		}
		if modelLess(b, a) {
			return false
		}
	}
	return false
}

package admission

import "slices"

func sdlMixedTransition(v any) error {
	if len(array(at(v, fieldEvidenceRefs))) == 0 || !effectiveInterval(v) || !numericSuccessor(at(v, "resulting_state_revision"), at(v, termExpectedStateRevision)) {
		return invalid()
	}
	proposal, revision := at(v, "proposal_ref") != nil, at(v, "proposal_revision") != nil
	if proposal != revision {
		return invalid()
	}
	switch stringAt(v, "transition_kind") {
	case termProposal:
		return require(!proposal)
	case termApproval, termDenial, "external-direction":
		return require(proposal)
	case termHandoff:
		return require(len(array(at(v, "completion_evidence_refs"))) > 0)
	default:
		return nil
	}
}

func sdlMixedOperation(v any) error {
	states, transitions := object(at(v, "controller_states")), object(at(v, "transitions"))
	if len(states) == 0 || len(transitions) == 0 || states[stringAt(v, "initial_state_ref")] == nil {
		return invalid()
	}
	if err := sdlMixedStateRevisions(v, states); err != nil {
		return err
	}
	ordered, err := sdlMixedOrdered(v, states, transitions)
	if err != nil {
		return err
	}
	if err := sdlMixedContinuity(v, ordered); err != nil {
		return err
	}
	return sdlMixedProposalLinks(transitions)
}

func sdlMixedStateRevisions(v any, states map[string]any) error {
	for _, state := range states {
		if !equal(at(state, fieldPolicyRevision), at(v, fieldPolicyRevision)) {
			return invalid()
		}
	}
	return nil
}

func sdlMixedOrdered(v any, states, transitions map[string]any) ([]any, error) {
	orders := map[string]bool{}
	ordered := make([]any, 0, len(transitions))
	for _, transition := range transitions {
		order, ok := number(at(transition, "effective_order"))
		if !ok || orders[order.RatString()] || !equal(at(transition, fieldPolicyRevision), at(v, fieldPolicyRevision)) || !sdlMixedEdgeStates(transition, states) {
			return nil, invalid()
		}
		orders[order.RatString()] = true
		ordered = append(ordered, transition)
	}
	slices.SortFunc(ordered, func(a, b any) int {
		left, _ := number(at(a, "effective_order"))
		right, _ := number(at(b, "effective_order"))
		return left.Cmp(right)
	})
	return ordered, nil
}

func sdlMixedEdgeStates(edge any, states map[string]any) bool {
	return states[stringAt(edge, "from_state_ref")] != nil && states[stringAt(edge, "to_state_ref")] != nil
}

func sdlMixedContinuity(v any, ordered []any) error {
	established := map[[2]string]bool{{stringAt(v, "initial_state_ref"), "0"}: true}
	for _, transition := range ordered {
		before, beforeOK := number(at(transition, termExpectedStateRevision))
		after, afterOK := number(at(transition, "resulting_state_revision"))
		if !beforeOK || !afterOK || !established[[2]string{stringAt(transition, "from_state_ref"), before.RatString()}] {
			return invalid()
		}
		established[[2]string{stringAt(transition, "to_state_ref"), after.RatString()}] = true
	}
	return nil
}

func sdlMixedProposalLinks(transitions map[string]any) error {
	for _, transition := range transitions {
		if at(transition, "proposal_ref") == nil {
			continue
		}
		proposal := transitions[stringAt(transition, "proposal_ref")]
		if stringAt(proposal, "transition_kind") != termProposal || !numericEqual(at(transition, "proposal_revision"), at(proposal, "resulting_state_revision")) || !numericGreater(at(transition, "effective_order"), at(proposal, "effective_order")) {
			return invalid()
		}
	}
	return nil
}

func sdlMixedPolicy(v any) error {
	states, transitions := object(at(v, "controller_states")), object(at(v, "permitted_transitions"))
	if states[stringAt(v, "initial_state_ref")] == nil {
		return invalid()
	}
	if err := sdlMixedStateRevisions(v, states); err != nil {
		return err
	}
	for _, state := range states {
		if countAt(state, termValidUntilOrder) > 1000000 {
			return invalid()
		}
	}
	for _, transition := range transitions {
		if !sdlMixedEdgeStates(transition, states) {
			return invalid()
		}
	}
	return sdlMixedScript(v, transitions)
}

func sdlMixedScript(v any, transitions map[string]any) error {
	steps := at(v, "script_steps")
	if stringAt(v, "form") == "reusable-policy" {
		return require(steps == nil)
	}
	if steps == nil || !uniqueRows(steps, "step_id") {
		return invalid()
	}
	for _, step := range array(steps) {
		if transitions[stringAt(step, "permitted_transition_ref")] == nil {
			return invalid()
		}
	}
	return nil
}

func sdlMixedScriptStep(v any) error {
	if (at(v, termValidFromOrder) == nil) != (at(v, termValidUntilOrder) == nil) || at(v, "target_step_ref") != nil && equal(at(v, "target_step_ref"), at(v, "step_id")) {
		return invalid()
	}
	return sdlOptionalInterval(v, termValidFromOrder, termValidUntilOrder)
}

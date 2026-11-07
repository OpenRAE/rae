package authoring

func (c materializedChecks) mixedControl() error {
	scopes := operatingScopeIndex(c.value)
	for _, raw := range object(c.value[behaviorSection]) {
		spec := object(raw)
		policy := object(spec["mixed_control"])
		if err := c.mixedPolicy(spec, policy, scopes); err != nil {
			return err
		}
	}
	return nil
}
func resolvedController(policy, state map[string]any) string {
	controller := text(state["controller_ref"])
	if controller == "self" {
		return text(policy["participant_ref"])
	}
	return controller
}
func (c materializedChecks) mixedState(spec, policy, state map[string]any, scopes *declarationIndex) error {
	controller := object(object(c.value[agentsSection])[resolvedController(policy, state)])
	if controller == nil {
		return semanticInvalid()
	}
	if err := c.controlRefsWithin(array(state["authority_basis_refs"]), array(controller["authority_anchors"]), c.index, "declared"); err != nil {
		return err
	}
	if err := c.controlRefsWithin(array(state[scopeRefsField]), array(spec[authorityScopeRefsField]), c.index, "scope"); err != nil {
		return err
	}
	actual, err := c.index.canonicalRefs(array(state[scopeRefsField]), "scope")
	if err != nil {
		return err
	}
	allowed, err := scopes.canonicalRefs(array(controller["operating_scope"]), "target")
	if err != nil {
		return err
	}
	if !refsWithin(actual, allowed) {
		return semanticInvalid()
	}
	_, err = c.index.canonicalRefs(array(state[evidenceRefsField]), "declared")
	return err
}
func (c materializedChecks) mixedTransition(policy, transition map[string]any, reusable bool) error {
	states := object(policy["controller_states"])
	source, destination := object(states[text(transition["from_state_ref"])]), object(states[text(transition["to_state_ref"])])
	if source["authority_status"] == revokedTerm {
		return semanticInvalid()
	}
	if reusable {
		if err := reusableTransition(policy, transition, source, destination); err != nil {
			return err
		}
	} else {
		if err := legacyTransition(policy, transition, source, destination); err != nil {
			return err
		}
	}
	refs := append(append([]any{}, array(transition[evidenceRefsField])...), array(transition["completion_evidence_refs"])...)
	_, err := c.index.canonicalRefs(refs, "declared")
	return err
}
func legacyProposalJoin(policy, transition map[string]any) error {
	if ref := text(transition["proposal_ref"]); ref != "" {
		proposal := object(object(policy["transitions"])[ref])
		if transition["from_state_ref"] != proposal["to_state_ref"] || !modelNumberEqual(transition["expected_state_revision"], proposal["resulting_state_revision"]) {
			return semanticInvalid()
		}
	}
	return nil
}
func modelNumberEqual(left, right any) bool {
	a, ok := modelInteger(left)
	b, present := modelInteger(right)
	return ok && present && a.Cmp(b) == 0
}
func modelLess(left, right any) bool {
	a, ok := modelInteger(left)
	b, present := modelInteger(right)
	return ok && present && a.Cmp(b) < 0
}
func mixedWindowContains(window map[string]any, coordinate any) bool {
	return !modelLess(coordinate, window["valid_from_order"]) && !modelLess(window["valid_until_order"], coordinate)
}
func mixedWindowsOverlap(left, right map[string]any) bool {
	return !modelLess(left["valid_until_order"], right["valid_from_order"]) && !modelLess(right["valid_until_order"], left["valid_from_order"])
}

func (c materializedChecks) mixedPolicy(spec, policy map[string]any, scopes *declarationIndex) error {
	if (spec["behavior_mode"] == "mixed-control") != (policy != nil) {
		return semanticInvalid()
	}
	if policy == nil {
		return nil
	}
	if !stringSet(array(spec[participantRefsField]))[text(policy["participant_ref"])] || policy["policy_revision"] != spec["semantic_version"] {
		return semanticInvalid()
	}
	states := object(policy["controller_states"])
	for _, rawState := range states {
		if err := c.mixedState(spec, policy, object(rawState), scopes); err != nil {
			return err
		}
	}
	if object(states[text(policy["initial_state_ref"])])["authority_status"] == revokedTerm {
		return semanticInvalid()
	}
	reusable := policy["semantics"] == "mixed-control-policy-occurrence/rev1"
	collection := "transitions"
	if reusable {
		collection = "permitted_transitions"
	}
	for _, rawTransition := range object(policy[collection]) {
		if err := c.mixedTransition(policy, object(rawTransition), reusable); err != nil {
			return err
		}
	}
	if reusable {
		if err := mixedScript(policy); err != nil {
			return err
		}
	}
	return nil
}

func reusableTransition(policy, transition, source, destination map[string]any) error {
	if destination["authority_status"] == revokedTerm || !mixedWindowsOverlap(transition, source) || !mixedWindowsOverlap(transition, destination) {
		return semanticInvalid()
	}
	changed := resolvedController(policy, source) != resolvedController(policy, destination)
	if (transition["transition_kind"] == "handoff") != changed {
		return semanticInvalid()
	}
	return nil
}
func legacyTransition(policy, transition, source, destination map[string]any) error {
	if !mixedWindowContains(source, transition["effective_order"]) || !mixedWindowContains(destination, transition["effective_order"]) {
		return semanticInvalid()
	}
	if err := legacyProposalJoin(policy, transition); err != nil {
		return err
	}
	if transition["transition_kind"] == "handoff" && source["controller_ref"] == destination["controller_ref"] {
		return semanticInvalid()
	}
	return nil
}

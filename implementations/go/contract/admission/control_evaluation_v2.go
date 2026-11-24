package admission

func controlEvaluationV2(v any) error {
	request, plan := at(v, "request"), at(v, "effect_plan")
	if err := controlRequest(request, true); err != nil {
		return err
	}
	if err := controlEffectPlan(plan); err != nil {
		return err
	}
	if err := controlInvocations(request, array(at(v, "invocations")), array(at(v, "results"))); err != nil {
		return err
	}
	if err := controlStateProposals(array(at(v, "state_proposals"))); err != nil {
		return err
	}
	if err := controlEffectBudgetV2(v); err != nil {
		return err
	}
	if err := controlParentDecisions(v); err != nil {
		return err
	}
	if err := controlRequestedEffects(v); err != nil {
		return err
	}
	if err := controlStateBindings(v); err != nil {
		return err
	}
	if err := controlParentRelease(v); err != nil {
		return err
	}
	return controlCommitSnapshot(v)
}

func controlParentDecisions(v any) error {
	if !equal(at(v, "effect_plan", "parent_crossing"), at(v, "request", "context", "crossing")) {
		return invalid()
	}
	decisions := map[string]any{}
	for _, result := range array(at(v, "results")) {
		if stringAt(result, "status") == termResolved && stringAt(result, "payload", termKind) == termDecision && stringAt(result, "payload", "disposition") != "abstain" && set(at(v, "request", "applicability", "required_slot_ids"))[stringAt(result, "slot_id")] {
			decisions[stringAt(result, "result_id")] = at(result, "payload")
		}
	}
	if !equalSet(rowSet(at(v, "effect_plan", "decisions"), termDecisionID), keySet(decisions)) {
		return invalid()
	}
	for _, decision := range array(at(v, "effect_plan", "decisions")) {
		if !matchingFields(decision, decisions[stringAt(decision, termDecisionID)], "disposition", "rule") {
			return invalid()
		}
	}
	return nil
}

func controlRequestedEffects(v any) error {
	requested := map[string]any{}
	for _, result := range array(at(v, "results")) {
		if stringAt(result, "status") != termResolved || stringAt(result, "payload", termKind) != termEffectRequest {
			continue
		}
		effect := at(result, "payload")
		id := stringAt(effect, "effect_id")
		if requested[id] != nil {
			return invalid()
		}
		requested[id] = effect
	}
	return require(equal(controlRows(at(v, "effect_plan", termEffects), "effect_id"), requested))
}

func controlStateBindings(v any) error {
	proposed, calls := controlRows(at(v, "state_proposals"), "invocation_id"), controlRows(at(v, "invocations"), "invocation_id")
	if !subsetSet(keySet(proposed), keySet(calls)) {
		return invalid()
	}
	for _, call := range calls {
		if stringAt(call, "state_input", termSource) != "tentative" {
			continue
		}
		predecessor := proposed[stringAt(call, "state_input", "predecessor_invocation_id")]
		if predecessor == nil || !equal(at(predecessor, "scope"), at(call, "state_input", "scope")) || !equal(at(predecessor, "after"), at(call, "state_input", "state")) {
			return invalid()
		}
	}
	results := controlRows(at(v, "results"), "slot_id")
	for id, item := range proposed {
		if err := controlProposedResult(item, calls[id], results); err != nil {
			return err
		}
	}
	return nil
}

func controlAdmittedEffectsV2(v any) map[string]bool {
	composition, plan := at(v, "composition"), at(v, "effect_plan")
	if stringAt(composition, "disposition") == termEligible && stringAt(plan, "parent_disposition") == termPermit {
		return set(at(plan, "runnable_effect_ids"))
	}
	if !equalSet(set(at(composition, "blockers")), map[string]bool{"parent:" + stringAt(plan, "parent_disposition"): true}) {
		return map[string]bool{}
	}
	base := controlBaseParent(array(at(plan, "decisions")), stringAt(plan, "incumbent_gate_disposition"))
	admitted := map[string]bool{}
	for _, effect := range array(at(plan, termEffects)) {
		id := stringAt(effect, "effect_id")
		if !set(at(plan, "runnable_effect_ids"))[id] {
			continue
		}
		if stringAt(plan, "parent_disposition") == termWithhold && base == termPermit {
			if stringAt(effect, "phase") == termRequiredPredecessor {
				admitted[id] = true
			}
		} else if (base == termDeny || base == termWithhold) && stringAt(plan, "parent_disposition") == base && stringAt(effect, "phase") == termIndependent && set(at(effect, "allowed_parent_dispositions"))[base] {
			admitted[id] = true
		}
	}
	return admitted
}

func controlCommitSnapshot(v any) error {
	eligible := controlAdmittedEffectsV2(v)
	commit, context := at(v, "commit"), at(v, "request", "context")
	if !equal(at(commit, "expected_history_heads"), at(context, "expected_history_heads")) || !equal(at(commit, "effects_consumed"), at(context, "effects_consumed")) || !subset(stringsOf(at(commit, "dispatchable_effect_ids")), eligible) {
		return invalid()
	}
	return controlCommitDigests(v, eligible)
}

func controlProposedResult(item, call any, results map[string]any) error {
	if !equal(at(call, "state_input", "scope"), at(item, "scope")) || !equal(at(call, "state_input", "state"), at(item, "before")) {
		return invalid()
	}
	found := false
	for _, slot := range stringsOf(at(call, "requested_slot_ids")) {
		found = found || equal(at(results[slot], "next_provider_state"), at(item, "after"))
	}
	if !found {
		return invalid()
	}
	return nil
}

func controlCommitDigests(v any, eligible map[string]bool) error {
	commit := at(v, "commit")
	for field, document := range map[string]any{"coverage_digest": at(v, "request", "applicability"), "decision_digest": at(v, "effect_plan")} {
		digest, err := controlDigest(document)
		if err != nil {
			return err
		}
		if stringAt(commit, field) != digest {
			return invalid()
		}
	}
	effects := []any{}
	for _, effect := range array(at(v, "effect_plan", termEffects)) {
		if eligible[stringAt(effect, "effect_id")] {
			effects = append(effects, effect)
		}
	}
	for field, documents := range map[string][]any{"result_digests": array(at(v, "results")), "state_proposal_digests": array(at(v, "state_proposals")), "effect_intent_digests": effects} {
		if err := controlDigestList(at(commit, field), documents); err != nil {
			return err
		}
	}
	return nil
}

func controlDigestList(observed any, documents []any) error {
	digests := make([]string, 0, len(documents))
	for _, document := range documents {
		digest, err := controlDigest(document)
		if err != nil {
			return err
		}
		digests = append(digests, digest)
	}
	return require(equal(stringsOf(observed), digests))
}

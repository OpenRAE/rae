package admission

func controlCutCoordinates(v any) error {
	if err := controlReferenceKinds(v, map[string]string{kindRun: kindRun, termApparatus: termApparatus, termCrossing: termCrossing, termAuthority: termAuthority, "memory_scope": "memory", termClock: termClock, termTrigger: termTrigger}); err != nil {
		return err
	}
	if !matchingFields(v, at(v, "subject"), "participant_address", "episode_id") || !equal(at(v, termPolicy, "decision_cut_ref"), at(v, "state_cut", "cut_ref")) || !effectiveInterval(at(v, termPolicy)) || numericGreater(at(v, termPolicy, "effective_order"), at(v, termOrder)) || numericGreater(at(v, termOrder), at(v, termPolicy, "valid_until_order")) {
		return invalid()
	}
	if len(rowSet(at(v, "provider_states"), "instance_id")) != len(array(at(v, "provider_states"))) {
		return invalid()
	}
	for _, field := range []string{"expected_history_heads", "inputs", "predecessors"} {
		if !uniqueValues(at(v, field)) {
			return invalid()
		}
	}
	for _, head := range array(at(v, "expected_history_heads")) {
		if stringAt(head, termKind) != "history" {
			return invalid()
		}
	}
	return controlRetainedClaims(v)
}

func controlRetainedClaims(v any) error {
	firings, claims := array(at(v, "rule_firings")), array(at(v, "prior_effect_claims"))
	consumed, valid := integer(at(v, "effects_consumed"))
	if len(rowTupleSet(firings, "rule_id", "rule_revision")) != len(firings) || len(rowSet(claims, "effect_id")) != len(claims) || !uniqueValues(controlClaimKeys(claims)) || !valid || consumed < len(claims) {
		return invalid()
	}
	epochs := map[string]map[string]bool{}
	for _, firing := range firings {
		epochs[join(stringAt(firing, "rule_id"), stringAt(firing, "rule_revision"))] = set(at(firing, "firing_epochs"))
	}
	for _, claim := range claims {
		key := at(claim, "key")
		if !equal(at(key, "run_ref"), at(v, kindRun, "ref")) || !equal(at(key, "trigger_root"), at(v, "trigger_root")) || !epochs[join(stringAt(key, "rule_id"), stringAt(key, "rule_revision"))][stringAt(key, "firing_epoch")] {
			return invalid()
		}
	}
	return nil
}

func controlClaimKeys(claims []any) []any {
	keys := make([]any, len(claims))
	for index, claim := range claims {
		keys[index] = at(claim, "key")
	}
	return keys
}

func controlResultPayloadV2(v any) error {
	if stringAt(v, "rule_outcome") == resultNotTriggered {
		if stringAt(v, "status") != termResolved || at(v, "payload") != nil || len(array(at(v, "evaluated_basis"))) == 0 {
			return invalid()
		}
	} else {
		if len(array(at(v, "evaluated_basis"))) > 0 || (stringAt(v, "status") == termResolved) != (at(v, "payload") != nil) {
			return invalid()
		}
	}
	return require(at(v, "next_provider_state") == nil || stringAt(v, "next_provider_state", termKind) == termProviderState && stringAt(v, "status") == termResolved)
}

func controlEffectPhase(v any) error {
	if err := controlEffectIdentity(v); err != nil {
		return err
	}
	if stringAt(v, termTrigger, termKind) != termTrigger || !fieldsUnique(v, "allowed_parent_dispositions") || !subset(stringsOf(at(v, "allowed_parent_dispositions")), map[string]bool{termPermit: true, termDeny: true, termWithhold: true}) {
		return invalid()
	}
	empty := len(array(at(v, "allowed_parent_dispositions"))) == 0
	switch stringAt(v, "phase") {
	case termRequiredPredecessor:
		return require(stringAt(v, "parent_outcome") == postureNone && empty)
	case termSuccessDependent:
		return require(stringAt(v, "parent_outcome") != postureNone && empty)
	case termIndependent:
		return require(stringAt(v, "parent_outcome") == postureNone && !empty)
	default:
		return invalid()
	}
}

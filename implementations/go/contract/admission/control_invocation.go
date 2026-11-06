package admission

func controlInvocations(request any, calls, outputs []any) error {
	if len(rowSet(calls, "invocation_id")) != len(calls) || len(rowSet(outputs, "result_id")) != len(outputs) || len(rowSet(outputs, "slot_id")) != len(outputs) {
		return invalid()
	}
	slots, bindings := controlRows(at(request, "selection", "slots"), "slot_id"), controlRows(at(request, "selection", termBindings), "instance_id")
	if err := controlInvocationCoverage(request, calls, outputs); err != nil {
		return err
	}
	results := controlRows(outputs, "slot_id")
	cutDigest, err := controlDigest(at(request, "context"))
	if err != nil {
		return err
	}
	for _, call := range calls {
		binding := bindings[stringAt(call, "instance_id")]
		if err := controlCallIdentity(call, binding, cutDigest); err != nil {
			return err
		}
		if err := controlCallState(call, request, calls, outputs); err != nil {
			return err
		}
		if err := controlCallPredecessors(call, slots, results); err != nil {
			return err
		}
		if err := controlCallResults(call, slots, results); err != nil {
			return err
		}
	}
	return nil
}

func controlCallIdentity(call, binding any, cutDigest string) error {
	if binding == nil {
		return invalid()
	}
	digest, err := controlDigest(binding)
	if err != nil {
		return err
	}
	return require(stringAt(call, "binding_digest") == digest && stringAt(call, "context_digest") == cutDigest && equal(at(call, "state_input", "scope"), at(binding, "state_scope")))
}

func controlCallState(call, request any, calls, outputs []any) error {
	if stringAt(call, "state_input", "source") == termCommitted {
		states := controlRows(at(request, "context", "provider_states"), "instance_id")
		return require(equal(at(call, "state_input", "state"), at(states[stringAt(call, "instance_id")], "state")))
	}
	predecessor := controlRows(calls, "invocation_id")[stringAt(call, "state_input", "predecessor_invocation_id")]
	if predecessor == nil || !equal(at(predecessor, "instance_id"), at(call, "instance_id")) {
		return invalid()
	}
	proposals := []any{}
	for _, result := range outputs {
		if set(at(predecessor, "requested_slot_ids"))[stringAt(result, "slot_id")] && at(result, "next_provider_state") != nil {
			proposals = append(proposals, at(result, "next_provider_state"))
		}
	}
	if len(proposals) == 0 {
		return invalid()
	}
	for _, proposal := range proposals {
		if !equal(proposal, at(call, "state_input", "state")) {
			return invalid()
		}
	}
	return nil
}

func controlCallPredecessors(call any, slots, results map[string]any) error {
	declared := map[string]string{}
	for _, slot := range stringsOf(at(call, "requested_slot_ids")) {
		for _, dependency := range array(at(slots[slot], "dependencies")) {
			declared[stringAt(dependency, "slot_id")] = stringAt(dependency, termKind)
		}
	}
	for _, slot := range stringsOf(at(call, "requested_slot_ids")) {
		if _, exists := declared[slot]; exists {
			return invalid()
		}
	}
	supplied := controlRows(at(call, "predecessor_inputs"), "slot_id")
	if len(supplied) != len(declared) {
		return invalid()
	}
	for id, item := range supplied {
		kind, exists := declared[id]
		if !exists {
			return invalid()
		}
		if err := controlPredecessorInput(call, item, kind, results); err != nil {
			return err
		}
	}
	return nil
}

func controlPredecessorInput(call, item any, kind string, results map[string]any) error {
	predecessor := results[stringAt(item, "slot_id")]
	if predecessor == nil || stringAt(item, termKind) != kind || !equal(at(predecessor, "result_id"), at(item, "result_id")) {
		return invalid()
	}
	digest, err := controlDigest(predecessor)
	if err != nil {
		return err
	}
	if digest != stringAt(item, "result_digest") {
		return invalid()
	}
	if !controlResultSatisfiedV2(predecessor) {
		for _, slot := range stringsOf(at(call, "requested_slot_ids")) {
			if stringAt(results[slot], "status") == termResolved {
				return invalid()
			}
		}
	}
	return nil
}

func controlResultSatisfiedV2(v any) bool {
	if stringAt(v, "status") != termResolved {
		return false
	}
	if stringAt(v, "payload", "domain") == termOwnerIfcRev1 {
		return stringAt(v, "payload", "sink_disposition") == termPermit
	}
	return stringAt(v, "rule_outcome") == resultNotTriggered || at(v, "payload") != nil && (stringAt(v, "payload", termKind) != termDecision || stringAt(v, "payload", "disposition") == termPermit)
}

func controlCallResults(call any, slots, results map[string]any) error {
	digest, err := controlDigest(call)
	if err != nil {
		return err
	}
	for _, id := range stringsOf(at(call, "requested_slot_ids")) {
		slot, result := slots[id], results[id]
		if !equal(at(slot, "instance_id"), at(call, "instance_id")) || !matchingFields(result, call, "instance_id", "binding_digest", "context_digest") || stringAt(result, "invocation_digest") != digest {
			return invalid()
		}
		if stringAt(result, "rule_outcome") == resultNotTriggered && stringAt(slot, termKind) != termEffectRequest || at(result, "payload") != nil && !equal(at(result, "payload", termKind), at(slot, termKind)) {
			return invalid()
		}
	}
	return nil
}

func controlInvocationCoverage(request any, calls, outputs []any) error {
	bySlot := map[string]any{}
	for _, call := range calls {
		for _, slot := range stringsOf(at(call, "requested_slot_ids")) {
			if bySlot[slot] != nil {
				return invalid()
			}
			bySlot[slot] = call
		}
	}
	expected := set(at(request, "applicability", "applicable_slot_ids"))
	if !sameKeys(bySlot, expected) || !equalSet(rowSet(outputs, "slot_id"), expected) {
		return invalid()
	}
	return nil
}

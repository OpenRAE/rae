package admission

func controlStateInput(v any) error {
	return require(stringAt(v, "state", termKind) == termProviderState && (stringAt(v, termSource) == "tentative") == (at(v, "predecessor_invocation_id") != nil))
}

func controlInvocationIdentity(v any) error {
	return require(fieldsUnique(v, "requested_slot_ids") && len(rowSet(at(v, "predecessor_inputs"), "slot_id")) == len(array(at(v, "predecessor_inputs"))) && stringAt(v, "projection", termKind) == "projection")
}

func controlStateProposal(v any) error {
	if err := controlReferenceKinds(v, map[string]string{"before": termProviderState, "after": termProviderState}); err != nil {
		return err
	}
	return require(!equal(at(v, "before"), at(v, "after")) && !equal(at(v, "invocation_id"), at(v, "predecessor_invocation_id")))
}

func controlCommitBoundary(v any) error {
	for _, head := range array(at(v, "expected_history_heads")) {
		if stringAt(head, termKind) != "history" {
			return invalid()
		}
	}
	if !fieldsUnique(v, "result_digests", "state_proposal_digests", "effect_intent_digests", "dispatchable_effect_ids") || stringAt(v, "status") != termCommitted && len(array(at(v, "dispatchable_effect_ids"))) > 0 {
		return invalid()
	}
	if (stringAt(v, "status") == termCommitted) != (at(v, termReceipt) != nil) {
		return invalid()
	}
	return require(at(v, termReceipt) == nil || stringAt(v, termReceipt, termKind) == termReceipt)
}

func controlContinuation(v any) error {
	claims := array(at(v, "realized_claims"))
	return require(stringAt(v, "source_commit_receipt", termKind) == termReceipt && len(rowSet(claims, "effect_id")) == len(claims) && uniqueValues(controlClaimKeys(claims)))
}

func controlStateProposals(proposals []any) error {
	if len(rowSet(proposals, "invocation_id")) != len(proposals) {
		return invalid()
	}
	scopes := map[string][]any{}
	for _, proposal := range proposals {
		if err := controlStateProposal(proposal); err != nil {
			return err
		}
		key, err := controlDigest(at(proposal, "scope"))
		if err != nil {
			return err
		}
		scopes[key] = append(scopes[key], proposal)
	}
	for _, writers := range scopes {
		if err := controlScopeWriters(writers); err != nil {
			return err
		}
	}
	return nil
}

func controlScopeWriters(writers []any) error {
	if len(writers) <= 1 {
		return require(len(writers) == 0 || at(writers[0], "predecessor_invocation_id") == nil)
	}
	var root any
	byParent := map[string]any{}
	for _, writer := range writers {
		if at(writer, "predecessor_invocation_id") == nil {
			if root != nil {
				return invalid()
			}
			root = writer
			continue
		}
		parent := stringAt(writer, "predecessor_invocation_id")
		if byParent[parent] != nil {
			return invalid()
		}
		byParent[parent] = writer
	}
	if root == nil {
		return invalid()
	}
	return controlScopeChain(root, byParent, len(writers))
}

func controlScopeChain(root any, byParent map[string]any, count int) error {
	current := root
	seen := map[string]bool{stringAt(root, "invocation_id"): true}
	for byParent[stringAt(current, "invocation_id")] != nil {
		successor := byParent[stringAt(current, "invocation_id")]
		id := stringAt(successor, "invocation_id")
		if seen[id] || !equal(at(successor, "before"), at(current, "after")) {
			return invalid()
		}
		seen[id] = true
		current = successor
	}
	return require(len(seen) == count)
}

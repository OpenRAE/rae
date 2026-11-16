package admission

func (h *replacementHistory) validateChild(slot string, parent, child any) (any, error) {
	origin := at(child, "replacement_origin")
	prior, err := h.childAuthority(slot, parent, child)
	if err != nil {
		return nil, err
	}
	run, err := h.childParentRun(parent, child)
	if err != nil {
		return nil, err
	}
	receipt, err := trialAttemptEvidence(parent, prior, at(run, "trial_provenance"), h.receipts[stringAt(prior, fieldPlanEntryID)])
	if err != nil {
		return nil, err
	}
	cleanup := at(parent, "cleanup_plans", stringAt(prior, "execution_controls", "cleanup_plan_ref"))
	if stringAt(receipt, "receipt_id") != stringAt(origin, "cleanup_receipt_ref") || !replacementReusable(cleanup, receipt) {
		return nil, invalid()
	}
	return run, nil
}
func (h *replacementHistory) childAuthority(slot string, parent, child any) (any, error) {
	origin := at(child, "replacement_origin")
	for _, field := range []string{"authoring_input_ref", "task_ref"} {
		if !equal(at(child, "input_refs", field), at(h.root, "input_refs", field)) {
			return nil, invalid()
		}
	}
	if !equal(at(child, "replacement_policy"), at(h.root, "replacement_policy")) || !equal(at(origin, "parent_plan_digest"), at(parent, "plan_digest")) {
		return nil, invalid()
	}
	prior := at(parent, "entries", stringAt(origin, "parent_entry_id"))
	var entry any
	for _, value := range object(at(child, "entries")) {
		entry = value
	}
	if prior == nil || !equal(at(prior, termRunID), at(origin, "parent_run_id")) {
		return nil, invalid()
	}
	for _, dimension := range []string{"condition_id", "block_id"} {
		if !equal(at(entry, "coordinate", dimension), at(h.root, "entries", slot, "coordinate", dimension)) {
			return nil, invalid()
		}
	}
	return prior, nil
}
func (h *replacementHistory) childParentRun(parent, child any) (any, error) {
	origin := at(child, "replacement_origin")
	run := h.byVersion[[2]string{stringAt(origin, "parent_run_id"), stringAt(origin, "parent_run_version")}]
	if run == nil || !set(at(h.root, "replacement_policy", "replace_on"))[stringAt(run, "run_status")] {
		return nil, invalid()
	}
	digest, err := jsonDigest(run)
	if err != nil || digest != stringAt(origin, "parent_run_digest") {
		return nil, invalid()
	}
	if at(parent, "replacement_origin") != nil && stringAt(run, "run_version") != "1" {
		return nil, invalid()
	}
	if !equal(at(run, "task_ref"), at(child, "input_refs", "task_ref")) || !equal(at(run, "trial_provenance", fieldPlanEntryID), at(origin, "parent_entry_id")) {
		return nil, invalid()
	}
	return run, nil
}

func replacementReusable(cleanup, receipt any) bool {
	claim := at(receipt, "clean_state_claim")
	disposition, mode := stringAt(claim, "disposition"), stringAt(cleanup, "clean_state", "mode")
	return stringAt(receipt, "cleanup_status") == outcomeSucceeded && claim != nil && disposition != "fresh-range-required" && equalSet(set(at(claim, "boundary_refs")), keySet(at(cleanup, "resource_boundaries"))) && (disposition != termDeclaredReusable || mode == termDeclaredReusable) && mode != "fresh-range-required"
}

package admission

func behaviorLifecycle(v any) error {
	phase := stringAt(v, "lifecycle_phase")
	if phase == "" {
		return require(at(v, "phase_realization") == nil && at(v, "admission_disposition") == nil && at(v, "operation_ref") == nil && at(v, "operation_state") == nil)
	}
	if at(v, "phase_realization") == nil || (phase == "selection_or_admission") != (at(v, "admission_disposition") != nil) {
		return invalid()
	}
	if phase != "execution_attempt" && (at(v, "operation_ref") != nil || at(v, "operation_state") != nil) {
		return invalid()
	}
	switch stringAt(v, "event_type") {
	case "action_attempted":
		return require(phase == "intent_or_proposal" || phase == "selection_or_admission" || phase == "execution_attempt")
	case "state_transition_recorded":
		return require(phase == "state_update_commit")
	case termObservationEmitted:
		return require(phase == "observation_emission")
	default:
		return nil
	}
}

func propositionTruth(v any) error {
	if !fieldsUnique(v, "evidence_refs", "unsupported_capability_refs") || !fieldsUnique(at(v, "probe_binding"), "capability_refs") {
		return invalid()
	}
	outcome := stringAt(v, "proposition_outcome")
	expected := propositionOutcome(v, outcome)
	if stringAt(v, "assertion_outcome") != expected || (outcome == statusUnknown) != (at(v, "indeterminacy_reason") != nil) || (outcome == statusUnsupported) != (len(array(at(v, "unsupported_capability_refs"))) > 0) {
		return invalid()
	}
	if binding := at(v, "probe_binding"); binding != nil && !equal(at(binding, "proposition_address"), at(v, "proposition_address")) {
		return invalid()
	}
	return propositionEvidence(v, outcome)
}

func propositionEvidence(v any, outcome string) error {
	if outcome != termTrue && outcome != termFalse {
		return nil
	}
	if stringAt(v, "evaluation_basis") == "observed-state" && (at(v, "probe_binding") == nil || len(array(at(v, "evidence_refs"))) == 0 || at(v, "temporal_context") == nil) {
		return invalid()
	}
	if stringAt(v, "evaluation_basis") == "declared-state" && at(v, "declared_artifact_digest") == nil {
		return invalid()
	}
	for _, loss := range array(at(v, "loss_disclosures")) {
		if !boolean(at(loss, "within_admissible_bound")) {
			return invalid()
		}
	}
	return nil
}

func propositionOutcome(v any, outcome string) string {
	if stringAt(v, "assertion_polarity") != "negative" {
		return outcome
	}
	switch outcome {
	case termTrue:
		return termFalse
	case termFalse:
		return termTrue
	default:
		return outcome
	}
}

func behaviorLifecycles(v any) error {
	for _, event := range array(v) {
		if err := behaviorLifecycle(event); err != nil {
			return err
		}
	}
	return nil
}

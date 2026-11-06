package admission

func (s *mixedStages) outcome() error {
	state := stringAt(s.history.outcome, "proposed_state")
	if s.history.outcome == nil || state != outcomeSucceeded && state != outcomeFailed {
		return nil
	}
	established := s.edgeState()
	if stringAt(s.subject, "kind") == termHandoff {
		established = s.handoffState()
	}
	return require(state == established)
}

func (s *mixedStages) refusedGrantState() string {
	if stringAt(s.seen[termTimeGrant], "comparison") == "incomparable" {
		return outcomeFailed
	}
	return outcomeIndeterminate
}

func (s *mixedStages) edgeState() string {
	execution := s.seen[termExecution]
	if execution == nil {
		return s.refusedGrantState()
	}
	if stringAt(execution, "status") == outcomeFailed {
		return outcomeFailed
	}
	if stringAt(execution, "status") == "succeeded" && s.seen[termDelivery] != nil && s.confirmed {
		return outcomeSucceeded
	}
	return outcomeIndeterminate
}

func (s *mixedStages) handoffState() string {
	handoff, readback := s.seen[termHandoff], s.seen[termOwnerReadback]
	if handoff == nil {
		return s.refusedGrantState()
	}
	if readback == nil || !s.confirmed {
		return outcomeIndeterminate
	}
	if stringAt(handoff, "status") == "committed" && equal(at(readback, "owner_component_id"), at(s.subject, "destination_component_id")) && equal(at(readback, "owner_ref"), at(s.subject, "destination_owner_ref")) && numericSuccessor(at(readback, "phase_revision"), at(handoff, "phase_revision")) {
		return outcomeSucceeded
	}
	status := stringAt(handoff, "status")
	if (status == outcomeFailed || status == termStale) && equal(at(readback, "owner_component_id"), at(s.subject, "source_component_id")) && equal(at(readback, "owner_ref"), at(s.subject, "source_owner_ref")) && equal(at(readback, "phase_revision"), at(handoff, "phase_revision")) {
		return outcomeFailed
	}
	return outcomeIndeterminate
}

func (s *mixedStages) citedReports() error {
	supplied := map[string]bool{}
	for _, report := range s.reports {
		digest, err := jsonDigest(report)
		if err != nil {
			return err
		}
		supplied[digest] = true
	}
	for _, response := range s.responses {
		message := at(response, "message")
		kind := stringAt(message, "kind")
		var references []any
		if kind == termProgress {
			references = array(at(message, "evidence_refs"))
		}
		if kind == messageOutcome || kind == messageReconciliation {
			references = array(at(message, "effects", "evidence_refs"))
		}
		for _, reference := range references {
			if stringAt(reference, termContractID) == termMixedBackendStageReportV1 && !supplied[stringAt(reference, termDigest)] {
				return invalid()
			}
		}
	}
	return nil
}

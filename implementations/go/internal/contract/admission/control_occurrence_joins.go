package admission

func (index *controlOccurrenceIndex) validate(record any) error {
	occurrence := at(record, "occurrence")
	declaration := index.declarations[join(stringAt(occurrence, "declaration_ref"), stringAt(record, fieldParticipantAddress), stringAt(record, fieldEpisodeID))]
	if declaration == nil || !matchingFields(record, declaration, fieldParticipantAddress, fieldEpisodeID) || !equal(at(record, "actor_ref"), at(declaration, "controller_ref")) || !matchingFields(occurrence, declaration, termKind, "controller_ref", "controller_state_ref", "authority_basis_refs", "controlled_scope_refs", "behavior_specification_ref", "mixed_control_policy_ref", "policy_revision", termExpectedStateRevision, "effective_order", termValidFromOrder, termValidUntilOrder) {
		return invalid()
	}
	if stringAt(occurrence, "disposition") == termRejected {
		return nil
	}
	switch stringAt(occurrence, termKind) {
	case termProposal:
		return index.transformedProposal(record)
	case termApproval, termDenial:
		return index.proposalDecision(record)
	case termHandoff:
		return require(equal(at(occurrence, "prior_controller_state_ref"), at(occurrence, "controller_state_ref")))
	default:
		return index.occurrenceTarget(record)
	}
}

func (index *controlOccurrenceIndex) transformedProposal(record any) error {
	occurrence := at(record, "occurrence")
	if at(occurrence, "source_proposal_ref") == nil {
		return nil
	}
	source := index.proposals[stringAt(occurrence, "source_proposal_ref")]
	if source == nil || !equal(at(occurrence, "source_proposal_revision"), at(source, "occurrence", "proposal_revision")) || !matchingFields(source, record, fieldParticipantAddress, fieldEpisodeID) || !subset([]string{stringAt(source, "event_id"), stringAt(occurrence, termTransformationRef)}, set(at(record, "provenance_refs"))) || !subset(stringsOf(at(source, "object_marking_refs")), set(at(record, "object_marking_refs"))) {
		return invalid()
	}
	return nil
}

func (index *controlOccurrenceIndex) proposalDecision(record any) error {
	occurrence := at(record, "occurrence")
	source := index.proposals[stringAt(occurrence, "proposal_ref")]
	if source == nil || !equal(at(occurrence, "proposal_revision"), at(source, "occurrence", "proposal_revision")) || !matchingFields(source, record, fieldParticipantAddress, fieldEpisodeID) || !numericGreater(at(occurrence, "effective_order"), at(source, "occurrence", "effective_order")) || !set(at(record, "predecessor_event_refs"))[stringAt(source, "event_id")] {
		return invalid()
	}
	return nil
}

func (index *controlOccurrenceIndex) occurrenceTarget(record any) error {
	occurrence := at(record, "occurrence")
	fields := map[string][]string{
		termExternalDirection: {termTargetKind, termTargetRef, termTargetRevision},
		termIntervention:      {"affected_target_kind", "affected_occurrence_ref", "affected_revision"},
		termOverride:          {"superseded_target_kind", "superseded_occurrence_ref", "superseded_revision"},
		termCancellation:      {termTargetKind, termTargetRef, termTargetRevision},
	}[stringAt(occurrence, termKind)]
	if len(fields) != 3 {
		return nil
	}
	target := index.targets[join(stringAt(occurrence, fields[0]), stringAt(occurrence, fields[1]))]
	return require(target != nil && equal(at(target, termTargetRevision), at(occurrence, fields[2])) && matchingFields(target, record, fieldParticipantAddress, fieldEpisodeID))
}

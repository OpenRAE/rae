package admission

type controlCitation struct {
	kind, reference string
	revision        any
}

func citedControlTarget(v any) (controlCitation, bool) {
	kind := stringAt(v, termKind)
	switch kind {
	case termProposal:
		if at(v, "source_proposal_ref") == nil {
			return controlCitation{}, false
		}
		return controlCitation{termProposal, stringAt(v, "source_proposal_ref"), at(v, "source_proposal_revision")}, true
	case termApproval, termDenial:
		return controlCitation{termProposal, stringAt(v, "proposal_ref"), at(v, "proposal_revision")}, true
	case termExternalDirection, termCancellation:
		return controlCitation{stringAt(v, "target_kind"), stringAt(v, "target_ref"), at(v, termTargetRevision)}, true
	case termIntervention:
		return controlCitation{stringAt(v, "affected_target_kind"), stringAt(v, "affected_occurrence_ref"), at(v, "affected_revision")}, true
	case termOverride:
		return controlCitation{stringAt(v, "superseded_target_kind"), stringAt(v, "superseded_occurrence_ref"), at(v, "superseded_revision")}, true
	default:
		return controlCitation{}, false
	}
}

func (f *controlEpisodeFold) target(v any) error {
	citation, present := citedControlTarget(v)
	if !present {
		return nil
	}
	sourceLink := stringAt(v, termKind) == termProposal
	if !sourceLink && !f.targetPermitted(v, citation) {
		return invalid()
	}
	produced, exists := f.produced[join(citation.kind, citation.reference)]
	if exists {
		if !equal(produced.revision, citation.revision) {
			return invalid()
		}
	} else if !f.externalTarget(v, citation) {
		return invalid()
	}
	if sourceLink || !exists {
		return nil
	}
	lifecycle := f.lifecycles[produced.event]
	proposals := map[string]bool{termApproval: true, termDenial: true, termExternalDirection: true, termCancellation: true}
	if citation.kind == termProposal && proposals[stringAt(v, termKind)] && (lifecycle.decided || lifecycle.superseded || lifecycle.replaced) {
		return invalid()
	}
	return require((stringAt(v, termKind) != termOverride && stringAt(v, termKind) != termCancellation) || !lifecycle.superseded)
}

func (f *controlEpisodeFold) externalTarget(v any, citation controlCitation) bool {
	for _, target := range f.available {
		if target.Target.ParticipantAddress == stringAt(f.policy, fieldParticipantAddress) && target.Target.EpisodeID == stringAt(f.policy, fieldEpisodeID) && target.Target.Kind == citation.kind && target.Target.Reference == citation.reference && numericEqual(target.Target.Revision, citation.revision) && numericGreater(at(v, "occurrence_revision"), target.AvailableAt) {
			return true
		}
	}
	return false
}

func (f *controlEpisodeFold) targetPermitted(v any, citation controlCitation) bool {
	transition := f.transitions[stringAt(v, "permitted_transition_ref")]
	step := f.steps[stringAt(v, "script_step_ref")]
	if !set(at(transition, "target_kinds"))[citation.kind] || at(step, "target_kind") != nil && stringAt(step, "target_kind") != citation.kind {
		return false
	}
	if at(step, "target_step_ref") == nil {
		return true
	}
	producer := f.stepRecords[stringAt(step, "target_step_ref")]
	produced, exists := f.produced[join(citation.kind, citation.reference)]
	return producer != "" && exists && produced.event == producer
}

func (f *controlEpisodeFold) citedLifecycle(v any) {
	citation, present := citedControlTarget(v)
	if !present {
		return
	}
	produced, exists := f.produced[join(citation.kind, citation.reference)]
	if !exists {
		return
	}
	lifecycle := f.lifecycles[produced.event]
	kind := stringAt(v, termKind)
	lifecycle.superseded = lifecycle.superseded || kind == termOverride || kind == termCancellation && (citation.kind == termProposal || citation.kind == termDecision)
	lifecycle.decided = lifecycle.decided || kind == termApproval || kind == termDenial
	lifecycle.replaced = lifecycle.replaced || kind == termProposal
	f.lifecycles[produced.event] = lifecycle
}

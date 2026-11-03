package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/ingress"

func (e *Validator) informationSources(v, profile any, sources map[string]InformationSource) error {
	for _, ref := range array(at(v, "source_refs")) {
		id, name := stringAt(ref, termContractID), stringAt(ref, "ref")
		if len(object(profile)) > 0 && !set(at(profile, "accepted_input_contracts"))[id] {
			return invalid()
		}
		source, exists := sources[join(id, name)]
		if !exists {
			return invalid()
		}
		if err := e.informationCoordinate(v, source.Coordinate); err != nil {
			return err
		}
		if err := e.informationSource(v, ref, source.Document); err != nil {
			return err
		}
	}
	return nil
}

func (e *Validator) informationCoordinate(v any, c InformationSourceCoordinate) error {
	cut, err := e.controlCut(c.StateCut)
	if err != nil {
		return err
	}
	return require(c.ParticipantAddress == stringAt(v, fieldParticipantAddress) && c.EpisodeID == stringAt(v, fieldEpisodeID) && c.AudienceScopeRef == stringAt(v, "audience_scope_ref") && c.VisibilityProjectionRef == stringAt(v, "visibility_projection_ref") && c.ProjectionPolicyRevision == stringAt(v, "projection_policy_revision") && c.RedactionPolicyRef == stringAt(v, "redaction_policy_ref") && c.RedactionPolicyRevision == stringAt(v, "redaction_policy_revision") && equal(cut, at(v, "state_cut")))
}

func (e *Validator) informationSource(v, ref any, raw []byte) error {
	id := stringAt(ref, termContractID)
	relations := map[string][]string{
		termParticipantObservationEnvelopeV1:        {basisObserved, termDisclosed},
		termParticipantContextViewV1:                {"derived", termDisclosed},
		termParticipantSharedStateRecordV1:          {basisObserved, termDisclosed, "shared_state_projection"},
		termParticipantBehaviorHistoryEventStreamV1: {basisObserved},
		termParticipantEpisodeStateEnvelopeV1:       {"authored_initial", "derived"},
	}
	allowed := false
	for _, relation := range relations[id] {
		allowed = allowed || relation == stringAt(ref, "relation")
	}
	if !allowed {
		return invalid()
	}
	if id == termParticipantBehaviorHistoryEventStreamV1 {
		return e.informationBehavior(v, raw)
	}
	source, err := e.contextDocument(id, raw)
	if err != nil {
		return err
	}
	if !matchingFields(v, source, fieldParticipantAddress, fieldEpisodeID) {
		return invalid()
	}
	return informationTypedSource(v, ref, source, id)
}

func informationTypedSource(v, ref, source any, id string) error {
	name := at(ref, "ref")
	switch id {
	case termParticipantObservationEnvelopeV1:
		if !equal(name, at(source, "observation_ref")) || !matchingFields(v, source, "visibility_projection_ref", "redaction_policy_ref") || at(source, "information_state_ref") != nil && !equal(at(source, "information_state_ref"), at(v, "information_state_ref")) {
			return invalid()
		}
		return informationSequence(v, at(source, "sequence_number"))
	case termParticipantContextViewV1:
		return require((equal(name, at(source, "view_id")) || equal(name, at(source, "view_ref"))) && matchingFields(v, source, "visibility_projection_ref", "redaction_policy_ref"))
	case termParticipantSharedStateRecordV1:
		if !equal(name, at(source, "event_id")) && !equal(name, at(source, "state_address")) || !equal(at(source, "visibility_projection_basis"), at(v, "visibility_projection_ref")) || !equal(at(source, "redaction_policy_ref"), at(v, "redaction_policy_ref")) {
			return invalid()
		}
		return informationSequence(v, at(source, "sequence_number"))
	case termParticipantEpisodeStateEnvelopeV1:
		if !equal(name, at(source, fieldEpisodeID)) {
			return invalid()
		}
		if stringAt(v, "state_cut", "history_domain") == "participant_episode_lifecycle" {
			return informationSequence(v, at(source, "sequence_number"))
		}
		return nil
	default:
		return invalid()
	}
}

func (e *Validator) informationBehavior(v any, raw []byte) error {
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err := e.low.CheckLocal(termParticipantBehaviorHistoryEventStreamV1, raw, limits); err != nil {
		return err
	}
	if err := e.checkModels(termParticipantBehaviorHistoryEventStreamV1, raw, limits); err != nil {
		return err
	}
	value, err := ingress.Parse(raw, limits, ingress.Array)
	if err != nil || len(array(value)) == 0 {
		return invalid()
	}
	for _, event := range array(value) {
		if !matchingFields(v, event, fieldParticipantAddress, fieldEpisodeID) {
			return invalid()
		}
		if err := informationSequence(v, at(event, "realized_order")); err != nil {
			return err
		}
	}
	return nil
}

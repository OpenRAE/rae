package admission

func (f *flowControl) sinks(v any) error {
	bindings := map[string]any{}
	for _, binding := range array(at(v, "bindings")) {
		if stringAt(binding, termKind) == termParticipantCrossing && stringAt(binding, "relation_target", "target_kind") == termSinkDecision {
			bindings[stringAt(binding, "stage_identity_ref")] = binding
		}
	}
	decisions := map[string]any{}
	for _, record := range f.crossings.records {
		if stringAt(record, "occurrence", "stage") == "decided" {
			decisions[stringAt(record, "occurrence", termDecisionID)] = at(record, "occurrence")
		}
	}
	for _, decision := range array(at(v, termSinkDecisions)) {
		if err := f.sink(decision, bindings, decisions); err != nil {
			return err
		}
	}
	return nil
}

func (f *flowControl) sink(v any, bindings, decisions map[string]any) error {
	admission := f.admissions[stringAt(v, "action_admission_ref")]
	a, hasAction := f.snapshot.ActionResolutions[stringAt(v, "action_admission_ref")]
	c, hasCapability := f.snapshot.CapabilityResolutions[stringAt(v, "capability_resolution_ref")]
	participant, episode, sink := stringAt(v, "subject", "participant_address"), stringAt(v, "subject", "episode_id"), flowSink(at(v, "sink"))
	if admission == nil || !hasAction || !hasCapability || a.ParticipantAddress != participant || a.EpisodeID != episode || a.Sink != sink || a.ActionContractAddress != stringAt(admission, "action_contract_address") || a.ActionInstanceID != stringAt(admission, "action_instance_id") || c.ParticipantAddress != participant || c.EpisodeID != episode || c.Sink != sink {
		return invalid()
	}
	key := flowHistoryKey(participant, episode, sink, stringsOf(at(v, "expected_history_head_refs")))
	history := ""
	for _, resolution := range f.snapshot.HistoryResolutions {
		if flowHistoryKey(resolution.ParticipantAddress, resolution.EpisodeID, resolution.Sink, resolution.Heads) == key {
			history = resolution.Disposition
			break
		}
	}
	if history == "" {
		return invalid()
	}
	crossing, binding := decisions[stringAt(v, "api_423_decision_ref")], bindings[stringAt(v, "api_423_decision_ref")]
	if crossing == nil || binding == nil || !equal(at(binding, "relation_target", "target_ref"), at(v, termDecisionID)) {
		return invalid()
	}
	expected := flowDisposition(stringAt(v, "confidentiality_result"), stringAt(v, "integrity_result"), flowCrossingDisposition(crossing), a.Disposition, c.Disposition, history)
	return require(stringAt(v, "final_disposition") == expected)
}

func flowCrossingDisposition(v any) string {
	switch stringAt(v, "disposition") {
	case termPermit, "transform":
		return termPermit
	case statusUnsupported:
		return statusUnsupported
	default:
		return termDeny
	}
}

package admission

import "slices"

func (f *flowControl) bindings(v any) error {
	for _, binding := range array(at(v, "bindings")) {
		var err error
		switch stringAt(binding, termKind) {
		case "runtime-fact":
			err = f.runtimeBinding(binding)
		case "action-argument":
			err = f.actionBinding(binding)
		case "participant-control":
			err = f.controlBinding(binding)
		case termParticipantCrossing:
			err = f.crossingBinding(binding)
		default:
			err = invalid()
		}
		if err != nil {
			return err
		}
	}
	return nil
}

func (f *flowControl) runtimeBinding(v any) error {
	plane := f.planes[stringAt(v, "plane_ref")]
	declaration := controlRows(at(plane, "declarations"), "fact_id")[stringAt(v, "declaration_ref")]
	version := controlRows(at(plane, "versions"), "version_id")[stringAt(v, "fact_version_ref")]
	sink := controlRows(at(plane, "sinks"), "sink_id")[stringAt(v, "sink_ref")]
	event := controlRows(at(plane, "events"), "event_id")[stringAt(v, "binding_event_ref")]
	if declaration == nil || version == nil || sink == nil || event == nil {
		return invalid()
	}
	return require(equal(at(version, "fact_id"), at(declaration, "fact_id")) && equal(at(event, "fact_id"), at(declaration, "fact_id")) && equal(at(event, "fact_version_id"), at(version, "version_id")) && equal(at(event, "sink_id"), at(sink, "sink_id")) && equal(at(v, "source_participant_address"), at(event, "participant_address")) && equal(at(v, "source_episode_id"), at(event, "episode_id")))
}

func (f *flowControl) actionBinding(v any) error {
	selection := f.selections[join(stringAt(v, "action_contract_address"), stringAt(v, "proposal_ref"))]
	if selection == nil {
		return invalid()
	}
	found := false
	for _, pair := range array(at(selection, "normalized_arguments")) {
		if len(array(pair)) == 2 && text(array(pair)[0]) == stringAt(v, "normalized_argument_name") {
			found = true
		}
	}
	admission := f.admissions[stringAt(v, "action_admission_ref")]
	return require(found && admission != nil && equal(at(admission, "action_contract_address"), at(v, "action_contract_address")) && equal(at(admission, "validated_selection"), selection) && equal(at(admission, "participant_address"), at(v, "source_participant_address")))
}

func flowSorted(v any) []string { values := stringsOf(v); slices.Sort(values); return values }

func (f *flowControl) controlBinding(v any) error {
	record := f.controls[stringAt(v, "event_id")]
	if record == nil {
		return invalid()
	}
	occurrence := at(record, "occurrence")
	identity, related := flowControlIdentity(occurrence)
	if identity == "" || !equal(at(v, "occurrence_kind"), at(occurrence, termKind)) || !equal(at(v, "occurrence_revision"), at(occurrence, "occurrence_revision")) || !matchingFields(v, record, "participant_address", "episode_id") || !equal(at(v, "controller_ref"), at(occurrence, "controller_ref")) || !equal(at(v, termAuthorityBasisRefs), flowSorted(at(occurrence, termAuthorityBasisRefs))) || !equal(at(v, "control_policy_revision"), at(occurrence, "policy_revision")) || stringAt(v, "occurrence_identity_ref") != identity || !equal(at(v, "related_occurrence_refs"), related) || !equal(at(v, "predecessor_event_refs"), flowSorted(at(record, "predecessor_event_refs"))) {
		return invalid()
	}
	return require(equal(at(v, "source_participant_address"), at(record, "participant_address")) && equal(at(v, "source_episode_id"), at(record, "episode_id")))
}

func flowControlIdentity(v any) (string, []string) {
	identity := ""
	fields := []string{}
	switch stringAt(v, termKind) {
	case "proposal":
		identity = "proposal_id"
		fields = []string{"source_proposal_ref", termTransformationRef}
	case "approval", "denial":
		identity = termDecisionRef
		fields = []string{"proposal_ref"}
	case "external-direction", "cancellation":
		identity = "target_ref"
	case "intervention":
		identity = "intervention_ref"
		fields = []string{"affected_occurrence_ref"}
	case termHandoff:
		identity = "resulting_controller_state_ref"
		fields = []string{"prior_controller_state_ref", "completion_evidence_ref"}
	case "override":
		identity = "replacement_ref"
		fields = []string{"superseded_occurrence_ref"}
	}
	return stringAt(v, identity), flowRelated(v, fields)
}

func flowRelated(v any, fields []string) []string {
	refs := []string{}
	for _, field := range fields {
		if at(v, field) != nil {
			refs = append(refs, stringAt(v, field))
		}
	}
	slices.Sort(refs)
	return refs
}

func (f *flowControl) crossingBinding(v any) error {
	record := f.crossings.records[stringAt(v, "event_id")]
	if record == nil {
		return invalid()
	}
	occurrence := at(record, "occurrence")
	subject, policy := at(occurrence, "subject"), at(occurrence, "policy")
	identity, related := flowCrossingIdentity(occurrence)
	if !equal(at(v, "stage"), at(occurrence, "stage")) || stringAt(v, "stage_identity_ref") != identity || !equal(at(v, "related_stage_refs"), related) || !matchingFields(v, record, "participant_address", "episode_id") || !matchingFields(v, subject, "subject_kind", "subject_ref", "subject_revision", "subject_digest") || !equal(at(v, "subject_contract_id"), at(subject, termContractID)) || !equal(at(v, "predecessor_event_refs"), flowSorted(at(record, "predecessor_event_refs"))) {
		return invalid()
	}
	for field, source := range map[string]string{"crossing_policy_id": "policy_id", "crossing_policy_revision": "policy_revision", "crossing_policy_digest": "policy_digest", "crossing_policy_decision_ref": "policy_decision_ref", "crossing_decision_cut_ref": "decision_cut_ref"} {
		if !equal(at(v, field), at(policy, source)) {
			return invalid()
		}
	}
	return require(matchingFields(at(v, "policy"), policy, "policy_id", "policy_revision", "policy_digest", "policy_decision_ref", "decision_cut_ref", "effective_order"))
}

func flowCrossingIdentity(v any) (string, []string) {
	identity := ""
	fields := []string{}
	switch stringAt(v, "stage") {
	case "requested":
		identity = "request_id"
		fields = []string{"action_or_projection_ref"}
	case "decided":
		identity = termDecisionID
		fields = []string{"request_ref"}
	case "transformed":
		return stringAt(v, "transformation_id"), flowSorted(jsonStrings([]string{stringAt(v, termDecisionRef), stringAt(v, "source_subject", "subject_ref"), stringAt(v, "result_subject", "subject_ref"), stringAt(v, "rule_ref")}))
	case termDisclosed:
		identity = "disclosure_id"
		fields = []string{termDecisionRef, termTransformationRef}
	case termDeliveryAttempted:
		identity = termAttemptID
		fields = []string{termDecisionRef, termTransformationRef, "owning_occurrence_ref"}
	case "delivered":
		identity = "delivery_id"
		fields = []string{termDecisionRef, "attempt_ref", "owning_occurrence_ref"}
	case basisObserved:
		identity = termObservationID
		fields = []string{termDecisionRef, "delivery_ref", "owning_observation_ref"}
	case "audited":
		identity = "audit_record_ref"
		fields = []string{"audited_event_ref"}
	}
	return stringAt(v, identity), flowRelated(v, fields)
}

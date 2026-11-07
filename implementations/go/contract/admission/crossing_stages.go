package admission

func (index *crossingIndex) stage(record any) error {
	v := at(record, "occurrence")
	switch stringAt(v, "stage") {
	case termRequested:
		return nil
	case termDecided:
		return crossingSuccessor(record, index.stages[join(termRequested, stringAt(v, "request_ref"))], true)
	case termTransformed:
		return index.transformation(record)
	case termDisclosed:
		return index.disclosure(record)
	case termDeliveryAttempted:
		return index.deliveryAttempt(record)
	case termDelivered:
		return index.delivery(record)
	case basisObserved:
		return index.observation(record)
	case termAudited:
		return crossingSuccessor(record, index.records[stringAt(v, "audited_event_ref")], true)
	default:
		return invalid()
	}
}

func crossingSuccessor(record, prior any, sameSubject bool) error {
	v, previous := at(record, "occurrence"), at(prior, "occurrence")
	if prior == nil || !matchingFields(record, prior, "participant_address", "episode_id") || !matchingFields(v, previous, "direction", "interaction_kind", "audience_scope_ref", "controller_ref", termAuthorityBasisRefs, termPolicy, "order_model") || sameSubject && !equal(at(v, "subject"), at(previous, "subject")) || !numericGreater(at(v, "effective_order"), at(previous, "effective_order")) || !set(at(record, "predecessor_event_refs"))[stringAt(prior, "event_id")] {
		return invalid()
	}
	return nil
}

func crossingPermitted(record any) bool {
	return record != nil && (stringAt(record, "occurrence", "disposition") == termPermit || stringAt(record, "occurrence", "disposition") == termTransform)
}

func crossingDeclassification(v, decision any) error {
	return require(stringAt(v, "operation") != termDeclassification || stringAt(decision, "occurrence", "gates", termDeclassification) == termPermit)
}

func (index *crossingIndex) transformation(record any) error {
	v := at(record, "occurrence")
	prior := index.stages[join(termDecided, stringAt(v, termDecisionRef))]
	if prior == nil || stringAt(prior, "occurrence", "disposition") != termTransform || !equal(at(v, "operation"), at(prior, "occurrence", "required_operation")) || crossingSubjectKey(at(v, "source_subject")) != crossingSubjectKey(at(prior, "occurrence", "subject")) {
		return invalid()
	}
	if err := crossingDeclassification(v, prior); err != nil {
		return err
	}
	return crossingSuccessor(record, prior, false)
}

func (index *crossingIndex) disclosure(record any) error {
	v := at(record, "occurrence")
	decision := index.stages[join(termDecided, stringAt(v, termDecisionRef))]
	if !crossingPermitted(decision) {
		return invalid()
	}
	if err := crossingDeclassification(v, decision); err != nil {
		return err
	}
	if at(v, termTransformationRef) == nil {
		if stringAt(decision, "occurrence", "disposition") == termTransform {
			return invalid()
		}
		return crossingSuccessor(record, decision, true)
	}
	transformed := index.stages[join(termTransformed, stringAt(v, termTransformationRef))]
	if transformed == nil || !equal(at(v, termDecisionRef), at(transformed, "occurrence", termDecisionRef)) {
		return invalid()
	}
	return crossingSuccessor(record, transformed, true)
}

func (index *crossingIndex) deliveryAttempt(record any) error {
	v := at(record, "occurrence")
	decision := index.stages[join(termDecided, stringAt(v, termDecisionRef))]
	if decision == nil || !equal(at(v, "owning_occurrence_ref"), at(v, "subject", "subject_ref")) {
		return invalid()
	}
	if stringAt(v, "disposition") == "withheld" {
		if stringAt(decision, "occurrence", "disposition") != termDeny || at(v, termTransformationRef) != nil {
			return invalid()
		}
		return crossingSuccessor(record, decision, true)
	}
	if !crossingPermitted(decision) {
		return invalid()
	}
	if stringAt(decision, "occurrence", "disposition") == termTransform {
		transformed := index.stages[join(termTransformed, stringAt(v, termTransformationRef))]
		if transformed == nil || !equal(at(v, termDecisionRef), at(transformed, "occurrence", termDecisionRef)) {
			return invalid()
		}
		return crossingSuccessor(record, transformed, true)
	}
	if at(v, termTransformationRef) != nil {
		return invalid()
	}
	return crossingSuccessor(record, decision, true)
}

func (index *crossingIndex) delivery(record any) error {
	v := at(record, "occurrence")
	decision := index.stages[join(termDecided, stringAt(v, termDecisionRef))]
	attempt := index.stages[join(termDeliveryAttempted, stringAt(v, "attempt_ref"))]
	if !crossingPermitted(decision) || attempt == nil || !equal(at(v, termDecisionRef), at(attempt, "occurrence", termDecisionRef)) || stringAt(attempt, "occurrence", "disposition") != "attempted" || numericGreater(at(v, "delivery_order"), at(v, "effective_order")) || !equal(at(v, "owning_occurrence_ref"), at(v, "subject", "subject_ref")) || !equal(at(v, "owning_occurrence_ref"), at(attempt, "occurrence", "owning_occurrence_ref")) {
		return invalid()
	}
	return crossingSuccessor(record, attempt, true)
}

func (index *crossingIndex) observation(record any) error {
	v := at(record, "occurrence")
	decision := index.stages[join(termDecided, stringAt(v, termDecisionRef))]
	delivery := index.stages[join(termDelivered, stringAt(v, termDeliveryRef))]
	if !crossingPermitted(decision) || delivery == nil || !equal(at(v, termDecisionRef), at(delivery, "occurrence", termDecisionRef)) || stringAt(delivery, "occurrence", "disposition") != termDelivered || numericGreater(at(v, "observation_order"), at(v, "effective_order")) || !equal(at(v, "owning_observation_ref"), at(v, "subject", "subject_ref")) {
		return invalid()
	}
	return crossingSuccessor(record, delivery, false)
}

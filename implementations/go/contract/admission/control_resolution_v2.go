package admission

func (r *controlResolution) validateV2(v any) error {
	if at(v, "continuation") != nil {
		return invalid()
	}
	crossing, _, err := r.optionalReference(r.snapshot.AdmittedCrossing)
	if err != nil {
		return err
	}
	if !equal(at(r.request, "context", "crossing"), crossing) || !equal(controlRows(at(r.request, "selection", termBindings), "instance_id"), r.indexes[termBindings]) || !equal(controlRows(at(r.request, "applicability", "coverage"), "obligation_id"), r.indexes["coverage"]) || !equal(controlRows(at(v, "results"), "slot_id"), r.indexes["results"]) {
		return invalid()
	}
	if err = r.supportV2(v); err != nil {
		return err
	}
	if err = r.effectsV2(v); err != nil {
		return err
	}
	return r.receiptsV2(v)
}

func (r *controlResolution) supportV2(v any) error {
	if len(r.snapshot.ResolvedSupport) != len(array(at(v, "support"))) || stringAt(v, "effect_plan", "incumbent_gate_disposition") != r.snapshot.IncumbentGateDisposition {
		return invalid()
	}
	remaining := 64 * 1048576
	for _, support := range array(at(v, "support")) {
		key := [2]string{stringAt(support, "obligation_id"), stringAt(support, "instance_id")}
		raw := r.snapshot.ResolvedSupport[key]
		if len(raw) > remaining {
			return invalid()
		}
		remaining -= len(raw)
		trusted, err := r.fragment("ControlSupportAssessmentV2Model", raw)
		if err != nil || !equal(support, trusted) {
			return invalid()
		}
		if controlSupportSatisfied(support) {
			ok, err := r.context.ControlSatisfiedSupport(controlRaw(support))
			if err != nil || !ok {
				return invalid()
			}
		}
	}
	return r.securityResultsV2(v)
}

func (r *controlResolution) securityResultsV2(v any) error {
	request := at(v, "request")
	obligations, results := controlRows(at(request, "selection", "obligations"), "obligation_id"), controlRows(at(v, "results"), "slot_id")
	if err := controlOwnerResultCoverage(request, results, obligations); err != nil {
		return err
	}

	for _, result := range results {
		binding := controlRows(at(request, "selection", termBindings), "instance_id")[stringAt(result, "instance_id")]
		if err := controlIFCResult(result, binding, at(request, "context")); err != nil {
			return err
		}
		if controlIsSecurityFact(at(result, "payload")) {
			if err := r.securityFact(at(result, "payload"), at(request, "context")); err != nil {
				return err
			}
		}
	}
	return nil
}

func (r *controlResolution) effectsV2(v any) error {
	if !equal(controlRows(at(v, "state_proposals"), "invocation_id"), r.indexes["proposals"]) {
		return invalid()
	}
	effects, outcomes := controlRows(at(v, "effect_plan", termEffects), "effect_id"), controlRows(at(v, "effect_plan", "effect_outcomes"), "effect_id")
	for _, id := range stringsOf(at(v, "effect_plan", "realized_effect_ids")) {
		if err := r.priorEffect(v, effects[id], outcomes[id]); err != nil {
			return err
		}
	}
	for id := range controlAdmittedEffectsV2(v) {
		if err := r.effectAuthority(effects[id], at(v, "request", "context")); err != nil {
			return err
		}
	}
	return nil
}

func (r *controlResolution) receiptsV2(v any) error {
	for field, raw := range map[string][]byte{"parent_admission_receipt": r.snapshot.ParentAdmissionReceipt, "parent_application_receipt": r.snapshot.ParentApplicationReceipt, "commit_receipt": r.snapshot.CommitReceipt} {
		trusted, _, err := r.optionalReference(raw)
		if err != nil {
			return err
		}
		observed := at(v, "effect_plan", field)
		if field == "commit_receipt" {
			observed = at(v, "commit", "receipt")
		}
		if !equal(observed, trusted) {
			return invalid()
		}
	}
	return require(equal(controlRows(at(v, "effect_plan", "effect_outcomes"), "effect_id"), r.indexes["receipts"]))
}

func (r *controlResolution) priorEffect(record, effect, outcome any) error {
	prior, ok := r.snapshot.CommittedIntents[stringAt(effect, "effect_id")]
	if !ok {
		return invalid()
	}
	origin, err := r.owner.contextDocument(termParticipantControlEvaluationV2, prior.Evaluation)
	if err != nil {
		return err
	}
	origin, err = r.owner.defaulted(termParticipantControlEvaluationV2, origin)
	if err != nil {
		return err
	}
	before, current := at(origin, "request", "context"), at(record, "request", "context")
	if !equal(controlRows(at(origin, "effect_plan", termEffects), "effect_id")[stringAt(effect, "effect_id")], effect) || !matchingFields(before, current, "run", "trigger_root", "subject", "participant_address", "episode_id") || numericGreater(at(before, "order"), at(current, "order")) || !numericGreater(at(current, "effects_consumed"), at(before, "effects_consumed")) {
		return invalid()
	}
	id := stringAt(effect, "effect_id")
	if stringAt(origin, "commit", "status") != termCommitted || at(origin, "commit", "receipt") == nil || !set(at(origin, "commit", "dispatchable_effect_ids"))[id] || !set(at(origin, "effect_plan", "runnable_effect_ids"))[id] || !controlAdmittedEffectsV2(origin)[id] {
		return invalid()
	}
	trusted, err := r.fragment("ControlRealizationBindingModel", prior.Outcome)
	if err != nil || !equal(trusted, outcome) || stringAt(trusted, "disposition") != termApplied {
		return invalid()
	}
	return r.effectAuthority(effect, before)
}

func controlOwnerResultCoverage(request any, results, obligations map[string]any) error {
	for _, coverage := range array(at(request, "applicability", "coverage")) {
		obligation := obligations[stringAt(coverage, "obligation_id")]
		if stringAt(coverage, "status") != termApplies || stringAt(obligation, "profile", "ref") != termParticipantOwnerFlowPolicyV1 {
			continue
		}
		for _, slot := range stringsOf(at(coverage, "slot_ids")) {
			result := results[slot]
			if stringAt(result, "status") == termResolved && (stringAt(result, "payload", termKind) != termIfcFact || !equal(at(result, "payload", "profile"), at(obligation, "profile"))) {
				return invalid()
			}
		}
	}
	return nil
}

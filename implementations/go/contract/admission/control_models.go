package admission

func (e *Validator) controlModel(name string, v any) (bool, error) {
	switch name {
	case "ControlEffectPlanV2Model":
		return true, controlEffectPlan(v)
	case "ControlStateScopeV2Model":
		return true, controlReferenceKinds(v, map[string]string{termAuthority: termAuthority})
	case "ControlStateInputV2Model":
		return true, controlStateInput(v)
	case "ControlInvocationV2Model":
		return true, controlInvocationIdentity(v)
	case "ControlStateProposalV2Model":
		return true, controlStateProposal(v)
	case "ControlCommitBoundaryV2Model":
		return true, controlCommitBoundary(v)
	case "ControlEffectContinuationV2Model":
		return true, controlContinuation(v)
	case "ControlParentDecisionV2Model":
		return true, controlReferenceKinds(v, map[string]string{"rule": "rule"})
	case termParticipantControlRequestModel:
		return true, controlRequest(v, false)
	case termParticipantControlRequestV2Model:
		return true, controlRequest(v, true)
	case "ControlObligationCoverageV2Model":
		return true, controlCoverageItem(v)
	case "ControlSubjectReferenceModel":
		return true, require(at(v, "subject_revision") != nil || at(v, "subject_digest") != nil)
	case "ControlPolicyReferenceModel":
		return true, require(effectiveInterval(v))
	case "ControlSequenceCutModel", "ControlCausalCutModel":
		return true, decisionCut(v)
	case "ControlProviderStateModel":
		return true, controlReferenceKinds(v, map[string]string{termState: termProviderState})
	case "ControlRuleFiringsModel":
		return true, require(fieldsUnique(v, "firing_epochs"))
	case termParticipantControlContextModel:
		return true, controlCutCoordinates(v)
	case "ControlCrossingEffectModel":
		return true, controlReferenceKinds(v, map[string]string{"crossing_decision": termCrossing})
	}
	return e.controlModelDetails(name, v)
}

func controlReferenceKinds(v any, fields map[string]string) error {
	for field, kind := range fields {
		if stringAt(v, field, termKind) != kind {
			return invalid()
		}
	}
	return nil
}

func controlTransformationEffect(v any) error {
	if err := controlReferenceKinds(v, map[string]string{termTransformation: termTransformation, "admission_policy": termPolicy}); err != nil {
		return err
	}
	return require(!equal(at(v, termSource, "subject_ref"), at(v, termResult, "subject_ref")))
}
func controlInjectEffect(v any) error {
	if err := controlReferenceKinds(v, map[string]string{termDeliveryRef: "inject-delivery", "disclosure_ref": termDisclosure}); err != nil {
		return err
	}
	return require(!equal(at(v, "source_item_ref"), at(v, "result_item_ref")))
}
func controlDelayEffect(v any) error {
	if err := controlReferenceKinds(v, map[string]string{termClock: termClock, "resumption_policy": termPolicy}); err != nil {
		return err
	}
	return require(!numericGreater(at(v, "earliest_order"), at(v, "latest_order")) && !numericGreater(at(v, "latest_order"), at(v, "expiry_order")))
}
func controlHandoffEffect(v any) error {
	if err := controlReferenceKinds(v, map[string]string{"transition": messageControl, "completion_obligation": "evidence"}); err != nil {
		return err
	}
	return require(!equal(at(v, "prior_controller_ref"), at(v, "resulting_controller_ref")))
}
func controlReviewEffect(v any) error {
	if err := controlReferenceKinds(v, map[string]string{"supervisor_authority": termAuthority, "approval_ref": messageControl, "denial_ref": messageControl, termClock: termClock, "resumption_policy": termPolicy}); err != nil {
		return err
	}
	return require(!equal(at(v, "approval_ref"), at(v, "denial_ref")))
}
func controlLifecycleEffect(v any) error {
	if err := controlReferenceKinds(v, map[string]string{"lifecycle_authority": termAuthority}); err != nil {
		return err
	}
	return require((stringAt(v, termKind) == termShutdown) == (stringAt(v, "operation") == "terminate"))
}
func controlEffectIdentity(v any) error {
	if err := controlReferenceKinds(v, map[string]string{termRule: termRule, termAuthority: termAuthority}); err != nil {
		return err
	}
	return require(equal(at(v, "key", "rule_id"), at(v, termRule, "ref")) && equal(at(v, "key", "rule_revision"), at(v, termRule, termRevision)) && fieldsUnique(v, "predecessor_effect_ids") && !set(at(v, "predecessor_effect_ids"))[stringAt(v, "effect_id")])
}

func controlResultPayload(v any) error {
	if (stringAt(v, "status") == termResolved) != (at(v, "payload") != nil) {
		return invalid()
	}
	return require(at(v, "next_provider_state") == nil || stringAt(v, "next_provider_state", termKind) == termProviderState && stringAt(v, "status") == termResolved)
}

func controlSupportAssessment(v any) error {
	for _, constraint := range array(at(v, "required_constraints")) {
		if stringAt(constraint, termKind) != termConstraint {
			return invalid()
		}
	}
	observed := at(v, "effective_support")
	if stringAt(v, "required_strength") == assuranceBounded && len(array(at(v, "required_constraints"))) == 0 || !equal(at(observed, "instance_id"), at(v, "instance_id")) {
		return invalid()
	}
	relation := stringAt(v, "relation")
	positive := relation == postureExact || relation == termBoundedCompatible || relation == termDisclosedWeakCompatible
	if positive && (stringAt(observed, "status") != termResolved || at(observed, "installation") == nil) {
		return invalid()
	}
	required, level := stringAt(v, "required_strength"), stringAt(observed, "effective_level")
	switch relation {
	case postureExact:
		return require(level == postureExact)
	case termBoundedCompatible:
		return require(required != postureExact && level == assuranceBounded)
	case termDisclosedWeakCompatible:
		return require(required == "disclosed_weak" && level == "disclosed_weak")
	case "insufficient", termUnresolved:
		return nil
	default:
		return invalid()
	}
}
func (e *Validator) controlModelDetails(name string, v any) (bool, error) {
	switch name {
	case "ControlTransformationEffectModel":
		return true, controlTransformationEffect(v)
	case "ControlInjectEffectModel":
		return true, controlInjectEffect(v)
	case "ControlDelayEffectModel":
		return true, controlDelayEffect(v)
	case "ControlHandoffEffectModel":
		return true, controlHandoffEffect(v)
	case "ControlReviewEffectModel":
		return true, controlReviewEffect(v)
	case "ControlLifecycleEffectModel":
		return true, controlLifecycleEffect(v)
	case "ControlAuditEffectModel":
		return true, controlReferenceKinds(v, map[string]string{"audit_record": "audit", "retention_policy": termPolicy})
	case "ControlEffectRequestModel":
		return true, controlEffectIdentity(v)
	case "ControlEffectRequestV2Model":
		return true, controlEffectPhase(v)
	case "ControlTeachingFactModel":
		return true, require(sortedUnique(stringsOf(at(v, "tokens"))))
	case "ControlSecurityFactModel":
		return true, controlReferenceKinds(v, map[string]string{"relation": "flow-relation"})
	case "ControlOwnerSecurityFactModel":
		if stringAt(v, "profile", "ref") != termParticipantOwnerFlowPolicyV1 || stringAt(v, "relation", termKind) != "flow-relation" {
			return true, invalid()
		}
		return true, e.controlProfile(at(v, "profile"))
	case "ControlDecisionModel":
		return true, controlReferenceKinds(v, map[string]string{termRule: termRule})
	case "ControlMechanismResultModel":
		return true, controlResultPayload(v)
	case "ControlMechanismResultV2Model":
		return true, controlResultPayloadV2(v)
	case "ControlCompositionModel":
		return true, require(fieldsUnique(v, "contributing_result_ids") && sortedUnique(stringsOf(at(v, "blockers"))))
	case "ControlRealizationBindingModel":
		return true, controlReferenceKinds(v, map[string]string{termReceipt: termReceipt})
	case "ControlSupportAssessmentV2Model":
		return true, controlSupportAssessment(v)
	default:
		return false, nil
	}
}

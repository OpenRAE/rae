package admission

import "github.com/OpenRAE/rae/implementations/go/contract/validation"

func (e *Validator) deliveryInvocationRules() map[string]definition {
	return map[string]definition{
		"participant-delivery-invocation-request-local-consistency": {check: deliveryInvocationRequest},
		"participant-delivery-invocation-context-local-consistency": {check: deliveryInvocationContext},
		// The outcome and the crossing evidence have no rule beyond their published shapes.
		"participant-delivery-invocation-outcome-local-consistency": {check: func(validation.Invocation) error { return nil }},
		"participant-crossing-evidence-local-consistency":           {check: func(validation.Invocation) error { return nil }},
	}
}

// implementationSelectionCompatible reports whether a selection binds the participant
// and the manifest identity, and uses only contracts, decision-surface modes and
// exposure policy kinds that the manifest supports.
func implementationSelectionCompatible(participant, manifest, selection any) bool {
	capabilities := at(manifest, "capabilities")
	return equal(at(selection, "participant_address"), participant) &&
		equal(at(manifest, termIdentity), at(selection, "implementation_identity")) &&
		subset(stringsOf(at(selection, "participant_contract_versions")), set(at(capabilities, "supported_participant_contracts"))) &&
		set(at(capabilities, "supported_decision_surface_modes"))[stringAt(selection, "selected_decision_surface_mode")] &&
		subset(stringsOf(at(selection, "exposure_policy", "exposure_policy_kinds")), set(at(capabilities, "exposure_policy_kinds")))
}

func deliveryInvocationRequest(i validation.Invocation) error {
	selection := at(i.Instance, "implementation_selection")
	return require(implementationSelectionCompatible(at(selection, "participant_address"), at(i.Instance, "implementation_manifest"), selection))
}

func deliveryInvocationContext(i validation.Invocation) error {
	v := i.Instance
	if err := participantInjectContent(at(v, "delivery")); err != nil {
		return err
	}
	return require(implementationSelectionCompatible(at(v, "delivery", "participant_address"), at(v, "implementation_manifest"), at(v, "implementation_selection")) && equal(at(v, "invocation_id"), at(v, "execution_scope_ref")))
}

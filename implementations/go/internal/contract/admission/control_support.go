package admission

func ownerFlowObligations(v any) error {
	bindings := map[string]any{}
	ownerProfiles := map[string]any{}
	for _, binding := range array(at(v, termBindings)) {
		if err := controlOwnerProfiles(binding, bindings, ownerProfiles); err != nil {
			return err
		}
	}
	for _, profile := range ownerProfiles {
		if err := ownerFlowProfileObligations(v, profile); err != nil {
			return err
		}
	}
	for _, obligation := range array(at(v, "obligations")) {
		for _, promise := range array(at(obligation, "admitted_support")) {
			if err := controlSupportPromise(obligation, promise, bindings); err != nil {
				return err
			}
		}
	}
	return nil
}
func controlSupportPromise(obligation, promise any, bindings map[string]any) error {
	binding := bindings[stringAt(promise, "instance_id")]
	if binding == nil {
		return invalid()
	}
	found := false
	for _, profile := range array(at(binding, "profiles")) {
		if equal(profile, at(obligation, termProfile)) {
			found = true
		}
	}
	if !found || stringAt(promise, "status") != termResolved || at(promise, "installation") == nil {
		return invalid()
	}
	level := stringAt(promise, "effective_level")
	required := stringAt(obligation, "required_strength")
	switch level {
	case postureExact:
		return nil
	case assuranceBounded:
		return require(required != postureExact)
	case termDisclosedWeak:
		return require(required == termDisclosedWeak)
	default:
		return invalid()
	}
}

func controlEffectiveSupport(v any) error {
	rank := map[string]int{statusUnsupported: 0, termDisclosedWeak: 1, assuranceBounded: 2, postureExact: 3}
	effective, declared := stringAt(v, "effective_level"), stringAt(v, "declared_level")
	if stringAt(v, "declaration_ref", termKind) != termManifest || rank[effective] > rank[declared] || effective != statusUnsupported && at(v, "installation") == nil {
		return invalid()
	}
	if at(v, "installation") != nil && stringAt(v, "installation", termKind) != "installation" {
		return invalid()
	}
	for field, kind := range map[string]string{"constraints": termConstraint, "limitations": "limitation"} {
		for _, ref := range array(at(v, field)) {
			if stringAt(ref, termKind) != kind {
				return invalid()
			}
		}
	}
	if effective == assuranceBounded && len(array(at(v, "constraints"))) == 0 {
		return invalid()
	}
	if at(v, "downgrade_authority") != nil {
		return require(stringAt(v, "downgrade_authority", termKind) == termAuthority && effective != statusUnsupported && effective != postureExact)
	}
	return nil
}

func ownerFlowProfileObligations(v, profile any) error {
	owned := map[string]bool{}
	for _, obligation := range array(at(v, "obligations")) {
		if equal(at(obligation, termProfile), profile) {
			owned[stringAt(obligation, "obligation_id")] = true
			if stringAt(obligation, "required_kind") != termIfcFact || len(array(at(obligation, "admitted_support"))) == 0 {
				return invalid()
			}
		}
	}
	if !equalSet(owned, map[string]bool{"ifc-owner-a": true, "ifc-owner-b": true}) {
		return invalid()
	}

	return nil
}

func controlOwnerProfiles(binding any, bindings, ownerProfiles map[string]any) error {
	bindings[stringAt(binding, "instance_id")] = binding
	for _, profile := range array(at(binding, "profiles")) {
		if stringAt(profile, "ref") == termParticipantOwnerFlowPolicyV1 {
			key, err := jsonDigest(profile)
			if err != nil {
				return err
			}
			ownerProfiles[key] = profile
		}
	}

	return nil
}

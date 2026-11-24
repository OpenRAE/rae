package admission

func sdlForwardingEdge(v any) error {
	classification := stringAt(v, "enrollment_identity_classification")
	return require(stringAt(v, "enrollment_identity_ref") == "" || variableRef(classification) || classification == termRedacted || classification == "operator_secret")
}

func sdlIdentityAttribute(v any) error {
	origin, provenance := text(defaultMember(v, "origin", statusUnknown)), text(defaultMember(v, "provenance", statusUnknown))
	return require(origin == statusUnknown || provenance == statusUnknown || origin == provenance)
}

func sdlSecretConsumer(v any) error {
	version, resolved := stringAt(v, "version_ref"), stringAt(v, "resolved_version_ref")
	if (version != "") == (at(v, "selector") != nil) || !fieldsUnique(v, "resolution_evidence_refs") {
		return invalid()
	}
	basis, evidence := at(v, "resolution_basis"), array(at(v, "resolution_evidence_refs"))
	if resolved == "" {
		return require(basis == nil && len(evidence) == 0)
	}
	if version != "" && version != resolved && !variableRef(version) && !variableRef(resolved) {
		return invalid()
	}
	return require(basis != nil && (basis != basisObserved || len(evidence) > 0))
}
func sdlServiceSecret(v any) error {
	if !fieldsUnique(v, "replica_locations") {
		return invalid()
	}
	return sdlUniqueCollections([2]string{"versions", "version_id"}, [2]string{"consumers", "selection_id"})(v)
}
func sdlAccessObservation(v any) error {
	if !fieldsUnique(v, "evidence_refs", "context_refs") {
		return invalid()
	}
	outcome := stringAt(v, "outcome")
	return require(outcome != "allowed" && outcome != "denied" || len(array(at(v, "evidence_refs"))) > 0)
}
func sdlPermissionBinding(v any) error {
	return require(fieldsUnique(v, "principal_refs", "resource_refs", "actions") && (len(array(at(v, "actions"))) > 0 || stringAt(v, "role_ref") != ""))
}
func sdlIdentityResourceAccess(v any) error {
	bindings := array(at(v, "bindings"))
	return require((stringAt(v, "inherited_from_ref") == "" || len(bindings) == 0) && sdlUniqueKey(bindings, termBindingID, false))
}
func sdlSecurityDefinition(v any) error {
	return require((stringAt(v, "canonical_digest") == "") == (stringAt(v, "digest_algorithm") == "") && !numericGreater(at(v, "source_start_line"), at(v, "source_end_line")))
}

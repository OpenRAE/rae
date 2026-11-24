package admission

import "github.com/OpenRAE/rae/implementations/go/contract/validation"

func (e *Validator) apparatusRules() map[string]definition {
	return map[string]definition{
		"canonical-apparatus-manifest-selected":           {check: apparatusSelected},
		"apparatus-constraint-identity-manifest-resolves": {check: apparatusConstraint},
		"apparatus-manifest-payload-identity-valid":       {check: e.apparatusManifests, contextual: true, requiresContext: true},
	}
}
func apparatusSelected(i validation.Invocation) error {
	v := i.Instance
	selected, subjects := map[string]bool{}, []string{}
	for _, ref := range array(at(v, "selected_manifests")) {
		selected[referenceKey(ref)] = true
		if subject := at(ref, "subject_ref"); subject != nil {
			subjects = append(subjects, join(stringAt(subject, fieldRefKind), stringAt(subject, fieldRefID), stringAt(subject, fieldRefVersion), stringAt(ref, fieldRefVersion)))
		}
	}
	if !unique(subjects) {
		return invalid()
	}
	canonical := map[string]bool{}
	for _, kind := range []string{kindProcessor, kindBackend} {
		component := at(v, termComponents, kind)
		if stringAt(component, "component_kind") != kind {
			return invalid()
		}
		if err := componentManifest(component, kind, kind+manifestV2Suffix, selected); err != nil {
			return err
		}
		canonical[referenceKey(at(component, "manifest_ref"))] = true
	}
	if err := participantManifests(at(v, termComponents), selected); err != nil {
		return err
	}
	for _, ref := range array(at(v, "selected_manifests")) {
		if at(ref, "ref_digest") != nil && !canonical[referenceKey(ref)] {
			return invalid()
		}
	}
	return require(rowSet(at(v, "observed_setup_evidence"), "role")["apparatus-evidence"])
}
func componentManifest(component any, kind, version string, selected map[string]bool) error {
	ref := at(component, "manifest_ref")
	subject := at(ref, "subject_ref")
	return require(ref != nil && subject != nil &&
		stringAt(subject, fieldRefKind) == kind && stringAt(ref, fieldRefVersion) == version &&
		equal(at(ref, fieldRefID), at(component, termIdentity, termName)) &&
		equal(at(subject, fieldRefID), at(component, termIdentity, termName)) && equal(at(subject, fieldRefVersion), at(component, termIdentity, "version")) &&
		at(subject, "ref_digest") == nil && at(subject, "ref_path") == nil && selected[referenceKey(ref)])
}
func participantManifests(components any, selected map[string]bool) error {
	for _, component := range object(components) {
		if stringAt(component, "component_kind") == kindParticipantImplementation {
			if err := componentManifest(component, kindParticipantImplementation, "participant-implementation-manifest/v1", selected); err != nil {
				return err
			}
		}
	}
	return nil
}
func apparatusConstraint(i validation.Invocation) error {
	v := i.Instance
	if len(array(at(v, "allowed_processor_refs")))+len(array(at(v, "allowed_backend_refs")))+len(array(at(v, "required_manifest_refs")))+len(array(at(v, "required_capabilities")))+len(array(at(v, "notes"))) == 0 {
		return invalid()
	}
	keys := map[string]bool{}
	for _, ref := range array(at(v, "required_manifest_refs")) {
		subject := at(ref, "subject_ref")
		if subject == nil {
			continue
		}
		if err := requiredManifest(ref, subject); err != nil {
			return err
		}
		keys[join(stringAt(subject, fieldRefKind), stringAt(subject, fieldRefID), stringAt(subject, fieldRefVersion), stringAt(ref, fieldRefVersion))] = true
	}
	for _, kind := range []string{kindProcessor, kindBackend} {
		for _, ref := range array(at(v, "allowed_"+kind+"_refs")) {
			if !keys[join(kind, stringAt(ref, fieldRefID), stringAt(ref, fieldRefVersion), kind+manifestV2Suffix)] {
				return invalid()
			}
		}
	}
	return nil
}
func requiredManifest(ref, subject any) error {
	kind := stringAt(subject, fieldRefKind)
	if (kind != kindProcessor && kind != kindBackend) || stringAt(ref, fieldRefVersion) != kind+manifestV2Suffix {
		return nil
	}
	return require(equal(at(ref, fieldRefID), at(subject, fieldRefID)) && at(subject, "ref_digest") == nil && at(subject, "ref_path") == nil)
}

package admission

import "github.com/OpenRAE/rae/implementations/go/contract/validation"

func (e *Validator) runJoinRules() map[string]definition {
	return map[string]definition{
		"result-evidence-ref-resolves":       {check: resultEvidence},
		"realized-form-evidence-refs-traced": {check: func(i validation.Invocation) error { return disclosureTraces(i.Instance, "realized_form_disclosures") }},
		"augmentation-disclosure-evidence-refs-traced": {check: func(i validation.Invocation) error {
			if !unique(rowIDs(at(i.Instance, "augmentation_disclosures"), "augmentation_id")) {
				return invalid()
			}
			return disclosureTraces(i.Instance, "augmentation_disclosures")
		}},
		"participant-implementation-provenance-resolves": {check: participantProvenance},
		"augmentation-disclosure-semantics-valid":        {check: augmentation},
	}
}
func resultEvidence(i validation.Invocation) error {
	ids := rowSet(at(i.Instance, "evidence_artifacts"), termArtifactID)
	for _, result := range object(at(i.Instance, "result_summaries")) {
		if !subset(rowIDs(at(result, fieldEvidenceRefs), fieldRefID), ids) {
			return invalid()
		}
	}
	return nil
}
func disclosureTraces(v any, field string) error {
	traced := map[string]bool{}
	for _, reference := range array(at(v, "traceability", "evidence_record_refs")) {
		traced[referenceKey(reference)] = true
	}
	for _, disclosure := range array(at(v, field)) {
		for _, reference := range array(at(disclosure, fieldEvidenceRefs)) {
			if !traced[referenceKey(reference)] {
				return invalid()
			}
		}
	}
	return nil
}
func participantProvenance(i validation.Invocation) error {
	v := i.Instance
	var participants []any
	for _, component := range object(at(v, "apparatus_context", termComponents)) {
		if stringAt(component, "component_kind") == kindParticipantImplementation {
			participants = append(participants, component)
		}
	}
	provenance := at(v, "participant_implementation_provenance")
	if provenance == nil {
		return require(len(participants) == 0)
	}
	if !equal(at(provenance, termRunID), at(v, termRunID)) {
		return invalid()
	}
	identities := map[string]bool{}
	for _, selection := range array(at(provenance, "participant_implementations")) {
		identities[join(stringAt(selection, "implementation_identity", termName), stringAt(selection, "implementation_identity", "version"))] = true
	}
	for _, component := range participants {
		if !identities[join(stringAt(component, termIdentity, termName), stringAt(component, termIdentity, "version"))] {
			return invalid()
		}
	}
	return nil
}
func augmentation(i validation.Invocation) error {
	v := i.Instance
	if !fieldsUnique(v, "classifications", "markings", "notes") {
		return invalid()
	}
	for _, field := range []string{"carrier_refs", "affected_refs", fieldEvidenceRefs} {
		if !uniqueReferences(at(v, field)) {
			return invalid()
		}
	}
	kind := stringAt(v, "augmented_by_ref", fieldRefKind)
	if kind != kindProcessor && kind != kindBackend {
		return invalid()
	}
	classifications := set(at(v, "classifications"))
	for term := range classifications {
		if term != "apparatus_only" && len(array(at(v, fieldEvidenceRefs))) == 0 {
			return invalid()
		}
	}
	return augmentationClaims(v, classifications)
}
func augmentationClaims(v any, classifications map[string]bool) error {
	if classifications["environment_visible"] {
		portable := map[string]bool{kindApparatusContext: true, "capture-spec": true, "derived-measure": true, "evidence-record": true, termManifest: true, "measurement-channel": true, termProfile: true, kindRun: true, kindScenarioSnapshot: true, kindMaterializationAttestation: true}
		found := false
		for _, carrier := range array(at(v, "carrier_refs")) {
			found = found || portable[stringAt(carrier, fieldRefKind)]
		}
		if at(v, "environment_effect") == nil || !found {
			return invalid()
		}
	}
	if classifications["participant_visible"] && (at(v, "participant_visibility") == nil || len(array(at(v, "markings"))) == 0) {
		return invalid()
	}
	if classifications["comparability_relevant"] && (at(v, "comparability_effect") == nil || at(v, "observer_effect") == nil) {
		return invalid()
	}
	return nil
}

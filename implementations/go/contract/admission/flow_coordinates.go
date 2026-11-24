package admission

import "slices"

func (f *flowControl) profileCoordinates(v any) error {
	confidentiality, integrity := set(at(f.profile, "confidentiality_obligation_refs")), set(at(f.profile, "integrity_obligation_refs"))
	for _, label := range array(at(v, termLabels)) {
		if err := f.profileLabel(label, confidentiality, integrity); err != nil {
			return err
		}
	}
	for _, release := range array(at(v, termReleases)) {
		for _, replacement := range array(at(release, "integrity_obligation_replacements")) {
			if !integrity[stringAt(replacement, "result_obligation_ref")] {
				return invalid()
			}
		}
	}
	for _, derivation := range array(at(v, termDerivations)) {
		if !matchingFields(derivation, at(f.profile, "derivation_rule"), "rule_ref", "rule_revision") {
			return invalid()
		}
	}
	return nil
}

func (f *flowControl) trustedCoordinates(v any) error {
	evidence := set(jsonStrings(f.context.CrossingEvidenceRefs()))
	if len(evidence) > 100000 {
		return invalid()
	}
	for _, field := range []string{termLabels, termDerivations, termReleases, termSinkDecisions, "bindings"} {
		if err := f.trustedRecordField(v, field, evidence); err != nil {
			return err
		}
	}
	produced := rowSet(at(v, termDerivations), "result_label_ref")
	for key := range rowSet(at(v, termReleases), "result_label_ref") {
		produced[key] = true
	}
	for _, label := range array(at(v, termLabels)) {
		if !produced[stringAt(label, "label_id")] && !equal(f.labels[stringAt(label, "label_id")], label) {
			return invalid()
		}
	}
	for _, release := range array(at(v, termReleases)) {
		if err := f.releaseCoordinate(release); err != nil {
			return err
		}
	}
	for _, decision := range array(at(v, termSinkDecisions)) {
		if !f.knownSink(flowSink(at(decision, "sink"))) {
			return invalid()
		}
	}
	return nil
}

func flowSink(v any) FlowSink {
	return FlowSink{Kind: stringAt(v, "sink_kind"), Reference: stringAt(v, "sink_ref"), Destination: stringAt(v, "destination_ref"), Audience: stringAt(v, "audience_scope_ref")}
}

func (f *flowControl) knownSink(sink FlowSink) bool {
	return slices.Contains(f.snapshot.KnownSinks, sink)
}

func (f *flowControl) releaseCoordinate(v any) error {
	expected := FlowReleaseAuthority{Kind: stringAt(v, termKind), Authority: stringAt(v, "authority_basis_ref"), Revision: stringAt(v, "authority_revision"), Sink: stringAt(v, "sink_ref"), Destination: stringAt(v, "destination_ref"), Audience: stringAt(v, "audience_scope_ref")}
	authorized := false
	for _, authority := range f.snapshot.ReleaseAuthorities {
		authorized = authorized || authority == expected
	}
	known := false
	for _, sink := range f.snapshot.KnownSinks {
		known = known || sink.Reference == expected.Sink && sink.Destination == expected.Destination && sink.Audience == expected.Audience
	}
	return require(authorized && known && set(jsonStrings(f.context.CrossingAuthorityRefs()))[expected.Authority])
}

func (f *flowControl) profileLabel(label any, confidentiality, integrity map[string]bool) error {
	if !subset(stringsOf(at(label, "confidentiality_obligation_refs")), confidentiality) || !subset(stringsOf(at(label, "integrity_obligation_refs")), integrity) {
		return invalid()
	}
	unknownC := set(at(label, "confidentiality_obligation_refs"))[stringAt(f.profile, "unknown_confidentiality_obligation_ref")]
	unknownI := set(at(label, "integrity_obligation_refs"))[stringAt(f.profile, "unknown_integrity_obligation_ref")]
	if stringAt(label, "resolution_status") == termResolved {
		if unknownC || unknownI {
			return invalid()
		}
	} else if !unknownC || !unknownI {
		return invalid()
	}

	return nil
}

func (f *flowControl) trustedRecordField(v any, field string, evidence map[string]bool) error {
	for _, record := range array(at(v, field)) {
		if !equal(f.cuts[stringAt(record, "policy", "decision_cut_ref")], at(record, "policy")) {
			return invalid()
		}
		if field != "bindings" && !subset(stringsOf(at(record, "evidence_refs")), evidence) {
			return invalid()
		}
	}

	return nil
}

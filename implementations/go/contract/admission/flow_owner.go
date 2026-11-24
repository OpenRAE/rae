package admission

func (f *flowControl) ownerCoordinates(v any) error {
	if stringAt(f.profile, termProfileID) != termParticipantOwnerFlowPolicyV1 {
		return nil
	}
	confidentiality, integrity := map[string]any{}, map[string]any{}
	readers, endorsed := map[string]bool{}, map[string]bool{}
	for _, clause := range array(at(f.profile, "owner_clauses")) {
		confidentiality[stringAt(clause, "confidentiality_obligation_ref")] = clause
		integrity[stringAt(clause, "untrusted_integrity_obligation_ref")] = clause
		endorsed[stringAt(clause, "endorsed_integrity_obligation_ref")] = true
		for _, reader := range stringsOf(at(clause, "reader_refs")) {
			readers[reader] = true
		}
	}
	for _, release := range array(at(v, termReleases)) {
		if err := f.ownerRelease(release, confidentiality, integrity); err != nil {
			return err
		}
	}
	labels := controlRows(at(v, termLabels), "label_id")
	for _, decision := range array(at(v, termSinkDecisions)) {
		if err := f.ownerSink(decision, labels, confidentiality, readers, endorsed); err != nil {
			return err
		}
	}
	return nil
}

func (f *flowControl) ownerRelease(v any, confidentiality, integrity map[string]any) error {
	digest, err := jsonDigest(v)
	if err != nil {
		return err
	}
	discharged := map[string]string{}
	if stringAt(v, termKind) == "declassification" {
		for _, token := range stringsOf(at(v, "removed_confidentiality_obligation_refs")) {
			discharged[token] = stringAt(confidentiality[token], "owner_ref")
		}
	} else {
		for _, replacement := range array(at(v, "integrity_obligation_replacements")) {
			token := stringAt(replacement, "source_obligation_ref")
			clause := integrity[token]
			if clause == nil || !equal(at(clause, "endorsed_integrity_obligation_ref"), at(replacement, "result_obligation_ref")) {
				return invalid()
			}
			discharged[token] = stringAt(clause, "owner_ref")
		}
	}
	return f.ownerReleaseGrants(digest, discharged)
}

func (f *flowControl) ownerSink(v any, labels, clauses map[string]any, knownReaders, endorsed map[string]bool) error {
	sink, ok := f.snapshot.OwnerSinks[flowSink(at(v, "sink"))]
	if !ok || len(sink.Readers) == 0 || len(sink.Readers) > 100000 || !subset(sink.Readers, knownReaders) {
		return invalid()
	}
	label := labels[stringAt(v, "label_ref")]
	c, i := statusUnsupported, statusUnsupported
	status := stringAt(label, "resolution_status")
	if status == termResolved {
		c, i = termSatisfied, termSatisfied
		for _, token := range stringsOf(at(label, "confidentiality_obligation_refs")) {
			if !subset(sink.Readers, set(at(clauses[token], "reader_refs"))) {
				c = termDeny
			}
		}
		if !sink.AcceptsUntrustedIntegrity && !subset(stringsOf(at(label, "integrity_obligation_refs")), endorsed) {
			i = termDeny
		}
	} else if status != statusUnsupported {
		c, i = termUnresolved, termUnresolved
	}
	return require(stringAt(v, "confidentiality_result") == c && stringAt(v, "integrity_result") == i)
}

func (f *flowControl) ownerReleaseGrants(digest string, discharged map[string]string) error {
	for token, owner := range discharged {
		if owner == "" {
			return invalid()
		}
		found := false
		expected := FlowOwnerReleaseAuthority{ReleaseDigest: digest, Owner: owner, Obligation: token}
		for _, authority := range f.snapshot.OwnerReleaseAuthorities {
			found = found || authority == expected
		}
		if !found {
			return invalid()
		}
	}
	return nil
}

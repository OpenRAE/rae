package comparison

import "slices"

func compareSubjects(input request, before, after ownerProjection, context context, reasons reasonSet) []change {
	beforeMap, afterMap := subjectMap(before.subjects), subjectMap(after.subjects)
	identities := []string{}
	for key := range beforeMap {
		identities = append(identities, key)
	}
	for key := range afterMap {
		identities = append(identities, key)
	}
	identities = sortedUnique(identities)
	if len(identities) > input.Limits.Subjects {
		identities = identities[:input.Limits.Subjects]
		reasons[reasonSubjects] = true
	}
	allowed := map[string]bool{}
	for _, identity := range identities {
		allowed[identity] = true
	}
	consumedBefore, consumedAfter := map[string]bool{}, map[string]bool{}
	result := []change{}
	for _, identity := range identities {
		old, oldOK := beforeMap[identity]
		next, newOK := afterMap[identity]
		if oldOK && newOK {
			result = append(result, pairedChange(old, next, relationSame, reasons))
			consumedBefore[identity], consumedAfter[identity] = true, true
		}
	}
	result = append(result, input.renamedChanges(context, beforeMap, afterMap, allowed, consumedBefore, consumedAfter, reasons)...)
	for _, identity := range identities {
		if _, present := afterMap[identity]; present && !consumedAfter[identity] {
			result = append(result, unpairedChange(identity, relationAdded))
		}
		if _, present := beforeMap[identity]; present && !consumedBefore[identity] {
			result = append(result, unpairedChange(identity, relationRemoved))
		}
	}
	slices.SortFunc(result, func(a, b change) int {
		return compareTuple([]string{a.Identity, stringValue(a.Before), stringValue(a.After)}, []string{b.Identity, stringValue(b.Before), stringValue(b.After)})
	})
	return result
}
func (input request) renamedChanges(context context, beforeMap, afterMap map[string]subject, allowed, consumedBefore, consumedAfter map[string]bool, reasons reasonSet) []change {
	result := []change{}
	renames := renameMap(input, context, reasons)
	oldNames := []string{}
	for old := range renames {
		oldNames = append(oldNames, old)
	}
	slices.Sort(oldNames)
	for _, oldName := range oldNames {
		newName := renames[oldName]
		old, oldOK := beforeMap[oldName]
		next, newOK := afterMap[newName]
		if oldOK && newOK && allowed[oldName] && allowed[newName] {
			result = append(result, pairedChange(old, next, "renamed", reasons))
			consumedBefore[oldName], consumedAfter[newName] = true, true
		}
	}

	return result
}
func subjectMap(input []subject) map[string]subject {
	result := make(map[string]subject, len(input))
	for _, item := range input {
		result[item.identity] = item
	}
	return result
}
func unpairedChange(identity, relation string) change {
	result := change{Identity: identity, IdentityRelation: relation, Textual: relationNotApplicable, Structural: relationNotApplicable, Semantic: relationNotApplicable, Reasons: []string{}}
	if relation == relationAdded {
		result.After = &identity
	} else {
		result.Before = &identity
	}
	return result
}
func pairedChange(before, after subject, relation string, aggregate reasonSet) change {
	reasons := reasonSet{}
	textual := digestRelation(before.representation, after.representation)
	if textual == "unknown" {
		reasons[reasonRepresentation], aggregate[reasonRepresentation] = true, true
	}
	structural, semantic := relationIncomparable, relationIncomparable
	if before.structuralProfile == after.structuralProfile {
		structural = digestRelation(before.structural, after.structural)
	}
	if before.semanticProfile == after.semanticProfile {
		semantic = digestRelation(before.semantic, after.semantic)
	}
	if structural == relationIncomparable || semantic == relationIncomparable {
		reasons["version-pair-incomparable"], aggregate["version-pair-incomparable"] = true, true
	}
	return change{Identity: after.identity, Before: &before.identity, After: &after.identity, IdentityRelation: relation, Textual: textual, Structural: structural, Semantic: semantic, Reasons: reasons.list()}
}
func digestRelation(before, after string) string {
	if before == "" || after == "" {
		return "unknown"
	}
	if before == after {
		return relationUnchanged
	}
	return relationChanged
}
func renameMap(input request, context context, reasons reasonSet) map[string]string {
	result := map[string]string{}
	report := context.report
	if report == nil {
		return result
	}
	switch {
	case report.Status != "success":
		reasons["transformation-evidence-not-successful"] = true
	case report.SourceDigest != input.Before.Digest || report.TargetDigest != input.After.Digest:
		reasons["transformation-evidence-digest-mismatch"] = true
	case report.SourceProfile != ownerProfile(input.Before) || report.TargetProfile != ownerProfile(input.After) || report.Canonicalization != input.Before.Canonicalization || report.Canonicalization != input.After.Canonicalization:
		reasons["transformation-evidence-profile-mismatch"] = true
	default:
		for _, mapping := range report.IdentityMap {
			result[mapping.Before] = mapping.After
		}
	}
	return result
}
func stringValue(input *string) string {
	if input == nil {
		return ""
	}
	return *input
}

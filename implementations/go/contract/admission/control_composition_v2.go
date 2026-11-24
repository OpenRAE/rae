package admission

import "slices"

func controlCompositionV2(v any) error {
	request, results, support := at(v, "request"), array(at(v, "results")), array(at(v, "support"))
	lost := array(at(v, "lost_advice"))
	if len(rowSet(results, "slot_id")) != len(results) || len(rowTupleSet(support, "obligation_id", "instance_id")) != len(support) || len(rowSet(lost, "slot_id")) != len(lost) {
		return invalid()
	}
	if err := controlSupportBindingsV2(request, support); err != nil {
		return err
	}
	failedOptional, err := controlLostAdvice(request, results, lost)
	if err != nil {
		return err
	}
	blockers, causes := controlCompositionCausesV2(request, results, support, at(v, "effect_plan"))
	disposition := termEligible
	for _, cause := range []string{"conflict", termStale, statusUnsupported, termWeakened, termDeny, termWithhold, outcomeFailed} {
		if causes[cause] {
			disposition = cause
			break
		}
	}
	contributors := rowIDs(results, "result_id")
	slices.Sort(contributors)
	composition := at(v, "composition")
	return require(stringAt(composition, "disposition") == disposition && sortedUnique(stringsOf(at(composition, "blockers"))) && equalSet(set(at(composition, "blockers")), blockers) && equal(stringsOf(at(composition, "contributing_result_ids")), contributors) && sortedUnique(stringsOf(at(composition, "lost_advice_slot_ids"))) && equalSet(set(at(composition, "lost_advice_slot_ids")), failedOptional))
}

func controlLostAdvice(request any, results, lost []any) (map[string]bool, error) {
	required := set(at(request, "applicability", "required_slot_ids"))
	failed := map[string]bool{}
	for _, result := range results {
		if !required[stringAt(result, "slot_id")] && !controlResultSatisfiedV2(result) {
			failed[stringAt(result, "slot_id")] = true
		}
	}
	if !equalSet(rowSet(lost, "slot_id"), failed) {
		return nil, invalid()
	}
	index := controlRows(results, "slot_id")
	for _, item := range lost {
		result := index[stringAt(item, "slot_id")]
		if at(result, "next_provider_state") != nil || at(result, "payload") != nil {
			return nil, invalid()
		}
	}
	return failed, nil
}

func controlCompositionCausesV2(request any, results, support []any, plan any) (map[string]bool, map[string]bool) {
	blockers, causes := map[string]bool{}, map[string]bool{}
	for _, coverage := range array(at(request, "applicability", "coverage")) {
		if stringAt(coverage, "status") == termUnresolved {
			blockers["coverage:"+stringAt(coverage, "obligation_id")] = true
			causes[termWithhold] = true
		}
	}
	index := controlRows(results, "slot_id")
	for _, id := range stringsOf(at(request, "applicability", "required_slot_ids")) {
		result := index[id]
		refusal := stringAt(result, "status") == termResolved && stringAt(result, "payload", termKind) == termDecision && (stringAt(result, "payload", "disposition") == termDeny || stringAt(result, "payload", "disposition") == termWithhold)
		if controlResultSatisfiedV2(result) || refusal {
			continue
		}
		blockers["slot:"+id] = true
		causes[controlRequiredResultCause(result)] = true
	}
	for _, item := range support {
		if cause := controlAdmittedSupportCause(request, item); cause != "" {
			blockers["support:"+stringAt(item, "obligation_id")+":"+stringAt(item, "instance_id")] = true
			causes[cause] = true
		}
	}
	if stringAt(plan, "parent_disposition") != termPermit {
		blockers["parent:"+stringAt(plan, "parent_disposition")] = true
		causes[stringAt(plan, "parent_disposition")] = true
	}
	return blockers, causes
}

func controlRequiredResultCause(v any) string {
	status := stringAt(v, "status")
	if status == termStale || status == statusUnsupported || status == termWeakened {
		return status
	}
	if stringAt(v, "payload", "domain") == termOwnerIfcRev1 {
		if stringAt(v, "payload", "sink_disposition") == termUnresolved {
			return termWithhold
		}
		return stringAt(v, "payload", "sink_disposition")
	}
	if stringAt(v, "payload", termKind) == termDecision && stringAt(v, "payload", "disposition") != "abstain" {
		return stringAt(v, "payload", "disposition")
	}
	return outcomeFailed
}

func controlParentRelease(v any) error {
	plan, commit := at(v, "effect_plan"), at(v, "commit")
	parentRelease := false
	for _, item := range array(at(v, "state_proposals")) {
		parentRelease = parentRelease || stringAt(item, "commit_on") == "parent-release"
	}
	if stringAt(commit, "status") == termCommitted && stringAt(plan, "parent_disposition") != termPermit && parentRelease {
		return invalid()
	}
	if err := controlCompositionV2(v); err != nil {
		return err
	}
	if stringAt(v, "composition", "disposition") == termEligible && stringAt(plan, "parent_disposition") == termPermit {
		return nil
	}
	return require(!boolean(at(plan, "parent_applied")) && at(plan, "parent_admission_receipt") == nil && at(plan, "parent_application_receipt") == nil && (stringAt(commit, "status") != termCommitted || !parentRelease))
}

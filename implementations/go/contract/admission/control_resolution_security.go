package admission

import "github.com/OpenRAE/rae/implementations/go/base/ingress"

func controlIsSecurityFact(v any) bool {
	return stringAt(v, termKind) == termIfcFact && (stringAt(v, "domain") == "sem-233/rev1" || stringAt(v, "domain") == termOwnerIfcRev1)
}

func (r *controlResolution) securityFact(fact, cut any) error {
	admitted := r.snapshot.FlowRelations[stringAt(fact, "relation", "ref")]
	if admitted.ContractID() != termParticipantFlowControlRelationV1 {
		return invalid()
	}
	original, err := ingress.Parse(admitted.JSON(), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return err
	}
	relation, err := r.owner.defaulted(admitted.ContractID(), original)
	if err != nil {
		return err
	}
	digest, err := controlDigest(relation)
	if err != nil || digest != stringAt(fact, "relation", termDigest) || !equal(at(relation, "document_id"), at(fact, "relation", "ref")) || !equal(at(relation, "document_revision"), at(fact, "relation", termRevision)) {
		return invalid()
	}
	if stringAt(fact, "domain") == termOwnerIfcRev1 {
		if !equal(at(relation, "profile", termProfileID), at(fact, "profile", "ref")) || !equal(at(relation, "profile", "profile_revision"), at(fact, "profile", termRevision)) || !equal(at(relation, "profile", "profile_digest"), at(fact, "profile", termDigest)) {
			return invalid()
		}
	} else if stringAt(relation, "profile", termProfileID) != termParticipantBoundaryFlowPolicyV1 {
		return invalid()
	}
	label := controlRows(at(relation, termLabels), "label_id")[stringAt(fact, "label_ref")]
	if stringAt(label, "resolution_status") != termResolved || !matchingFields(at(label, "policy"), at(cut, "policy"), "policy_id", "policy_revision", "policy_digest", "policy_decision_ref", "decision_cut_ref", "effective_order") {
		return invalid()
	}
	return controlSecuritySink(relation, fact, cut)
}

func controlSecuritySink(relation, fact, cut any) error {
	decisions := map[string]bool{}
	for _, binding := range array(at(relation, termBindings)) {
		if stringAt(binding, termKind) == termParticipantCrossing && equal(at(binding, "event_id"), at(cut, "crossing", "ref")) && stringAt(binding, "relation_target", "target_kind") == termSinkDecision {
			decisions[stringAt(binding, "relation_target", "target_ref")] = true
		}
	}
	for _, decision := range array(at(relation, termSinkDecisions)) {
		if controlSecurityDecision(decision, decisions, fact, cut) {
			return nil
		}
	}
	return invalid()
}

func controlSecurityDecision(v any, ids map[string]bool, fact, cut any) bool {
	if !ids[stringAt(v, termDecisionID)] || !equal(at(v, "label_ref"), at(fact, "label_ref")) || !equal(at(v, "sink", "sink_ref"), at(cut, "sink_ref")) || !equal(at(v, "sink", "destination_ref"), at(cut, "destination_ref")) || !equal(at(v, "sink", "audience_scope_ref"), at(cut, "audience_ref")) || !equalSet(set(at(v, "expected_history_head_refs")), rowSet(at(cut, "expected_history_heads"), "ref")) {
		return false
	}
	return stringAt(fact, "domain") != termOwnerIfcRev1 || equal(at(v, termDecisionID), at(fact, "sink_decision_ref")) && equal(at(v, "final_disposition"), at(fact, "sink_disposition"))
}

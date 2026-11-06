package admission

import "strings"

func controlSupportKeys(request any) map[string]bool {
	slots := controlRows(at(request, "selection", "slots"), "slot_id")
	roots, required := map[string]bool{}, map[string]bool{}
	for _, item := range array(at(request, "applicability", "coverage")) {
		if stringAt(item, "status") != "applies" {
			continue
		}
		for _, id := range stringsOf(at(item, "slot_ids")) {
			roots[id] = true
			required[join(stringAt(item, "obligation_id"), stringAt(slots[id], "instance_id"))] = true
		}
	}
	for _, id := range stringsOf(at(request, "applicability", "required_slot_ids")) {
		if !roots[id] {
			required[join("input:"+id, stringAt(slots[id], "instance_id"))] = true
		}
	}
	return required
}

func controlSupportBindingsV2(request any, support []any) error {
	if len(rowTupleSet(support, "obligation_id", "instance_id")) != len(support) || !equalSet(rowTupleSet(support, "obligation_id", "instance_id"), controlSupportKeys(request)) {
		return invalid()
	}
	digest, err := controlDigest(at(request, "context"))
	if err != nil {
		return err
	}
	obligations, slots := controlRows(at(request, "selection", "obligations"), "obligation_id"), controlRows(at(request, "selection", "slots"), "slot_id")
	for _, item := range support {
		if err := controlSupportBinding(item, obligations, slots, digest); err != nil {
			return err
		}
	}
	return nil
}

func controlSupportSatisfied(v any) bool {
	return map[string]bool{postureExact: true, termBoundedCompatible: true, termDisclosedWeakCompatible: true}[stringAt(v, "relation")]
}

func controlSupportPreserved(promise, observed any) bool {
	return stringAt(observed, "status") == termResolved && matchingFields(promise, observed, "instance_id", "feature", "declaration_ref", "declared_level", "effective_level", "installation", "constraints", "limitations") && subsetSet(rowTupleSet(at(promise, "evidence"), termKind, "ref", termRevision, termDigest), rowTupleSet(at(observed, "evidence"), termKind, "ref", termRevision, termDigest))
}

func controlAdmittedSupportCause(request, item any) string {
	observed := at(item, "effective_support")
	if !controlSupportSatisfied(item) {
		status := stringAt(observed, "status")
		if status == termStale || status == statusUnsupported || status == termWeakened {
			return status
		}
		if stringAt(observed, "effective_level") == statusUnsupported {
			return statusUnsupported
		}
		if status == termResolved {
			return termWeakened
		}
		return outcomeFailed
	}
	obligation := controlRows(at(request, "selection", "obligations"), "obligation_id")[stringAt(item, "obligation_id")]
	if obligation != nil {
		promise := controlRows(at(obligation, "admitted_support"), "instance_id")[stringAt(item, "instance_id")]
		if promise != nil && !controlSupportPreserved(promise, observed) {
			return termWeakened
		}
	}
	return ""
}

func controlSupportBinding(item any, obligations, slots map[string]any, digest string) error {
	if stringAt(item, "effective_support", "context_digest") != digest {
		return invalid()
	}
	if obligation := obligations[stringAt(item, "obligation_id")]; obligation != nil {
		if !equal(at(item, "required_strength"), at(obligation, "required_strength")) || !equal(at(item, "required_constraints"), at(obligation, "constraints")) {
			return invalid()
		}
	}
	if id, present := strings.CutPrefix(stringAt(item, "obligation_id"), "input:"); present {
		slot := slots[id]
		if slot == nil || !equal(at(item, "required_strength"), at(slot, "required_strength")) || !equal(at(item, "required_constraints"), at(slot, "constraints")) {
			return invalid()
		}
	}
	return nil
}

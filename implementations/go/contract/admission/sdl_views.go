package admission

import "slices"

func sdlSensitiveBoundary(kind string) bool {
	return slices.Contains([]string{"hidden_truth", "private_answer_key", "canary", "holdout_variant", "adjudication_material"}, kind)
}
func sdlExposedView(disposition string) bool {
	return slices.Contains([]string{termDiscovered, termInferred, termDisclosed, termDeceptive}, disposition)
}
func sdlViewRule(v any) error {
	disposition, disclosure := stringAt(v, "disposition"), stringAt(v, "disclosure_rule")
	if disposition == termDisclosed && disclosure == "" {
		return invalid()
	}
	if sdlSensitiveBoundary(stringAt(v, "boundary_class")) && (disposition == "observable" || sdlExposedView(disposition) && disclosure == "") {
		return invalid()
	}
	return require(disposition != "evidence_only" || len(array(at(v, fieldEvidenceRefs))) > 0)
}
func sdlViewTransition(v any) error {
	targets := map[string][]string{"discovery": {termDiscovered}, "inference": {termInferred}, "concealment": {"concealed"}, termDisclosure: {termDisclosed}, "revocation": {"hidden", "concealed"}, "deception": {termDeceptive}}
	kind, target := stringAt(v, "transition_kind"), stringAt(v, "to_disposition")
	if !slices.Contains(targets[kind], target) || target == stringAt(v, "from_disposition") || kind == termDisclosure && stringAt(v, "disclosure_rule") == "" {
		return invalid()
	}
	order, ok := number(at(v, "effective_order"))
	if !ok || !order.IsInt() || order.Sign() < 0 || len(array(at(v, fieldEvidenceRefs))) == 0 {
		return invalid()
	}
	return require((stringAt(v, "history_event_type") == "episode_close") == (at(v, "action_instance_id") == nil))
}

func sdlObservationBoundary(v any) error {
	observable, hidden, evidence := set(at(v, "observable_refs")), set(at(v, "hidden_refs")), set(at(v, fieldEvidenceRefs))
	if len(observable)+len(evidence) == 0 {
		return invalid()
	}
	rules, evidenceOnly := map[string]any{}, map[string]bool{}
	for _, rule := range array(at(v, "view_rules")) {
		ref := stringAt(rule, "information_ref")
		if rules[ref] != nil {
			return invalid()
		}
		rules[ref] = rule
		evidenceOnly[ref] = stringAt(rule, "disposition") == "evidence_only"
	}
	for ref := range hidden {
		if observable[ref] || evidence[ref] && !evidenceOnly[ref] {
			return invalid()
		}
	}
	for ref := range observable {
		if evidenceOnly[ref] {
			return invalid()
		}
	}
	return sdlViewSequence(array(at(v, "view_transitions")), rules)
}

func sdlViewSequence(transitions []any, rules map[string]any) error {
	relation := map[string]string{}
	for ref, rule := range rules {
		relation[ref] = stringAt(rule, "disposition")
	}
	ids, orders := map[string]bool{}, map[string]bool{}
	sequence := slices.Clone(transitions)
	slices.SortFunc(sequence, func(a, b any) int {
		order, _ := referenceNumberCompare(at(a, "effective_order"), at(b, "effective_order"))
		return order
	})
	for _, transition := range sequence {
		id, order := stringAt(transition, "transition_id"), sdlScalarIdentity(at(transition, "effective_order"))
		if ids[id] || orders[order] {
			return invalid()
		}
		ids[id], orders[order] = true, true
		ref, target := stringAt(transition, "information_ref"), stringAt(transition, "to_disposition")
		if rules[ref] == nil || relation[ref] != stringAt(transition, "from_disposition") || relation[ref] == target {
			return invalid()
		}
		if sdlSensitiveBoundary(stringAt(rules[ref], "boundary_class")) && sdlExposedView(target) && stringAt(transition, "disclosure_rule") == "" {
			return invalid()
		}
		relation[ref] = target
	}
	return nil
}

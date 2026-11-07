package authoring

func mixedTargets(transition map[string]any) map[string]bool {
	switch transition["transition_kind"] {
	case "approval", "denial":
		return map[string]bool{proposalTerm: true}
	case "external-direction":
		return stringSet(array(transition["target_kinds"]))
	case "intervention":
		return map[string]bool{"action": true, controlTerm: true, "attempt": true}
	case "override":
		return map[string]bool{controlTerm: true, decisionTerm: true}
	case "cancellation":
		return map[string]bool{proposalTerm: true, decisionTerm: true, "admitted-action": true, "attempt": true}
	default:
		return map[string]bool{}
	}
}
func mixedScript(policy map[string]any) error {
	earlier := map[string]string{}
	for _, raw := range array(policy["script_steps"]) {
		step := object(raw)
		transition := object(object(policy["permitted_transitions"])[text(step["permitted_transition_ref"])])
		if err := mixedScriptWindow(policy, step, transition); err != nil {
			return err
		}
		allowed := mixedTargets(transition)
		if target := text(step["target_kind"]); target != "" {
			if !allowed[target] {
				return semanticInvalid()
			}
			allowed = map[string]bool{target: true}
		}
		if ref := text(step["target_step_ref"]); ref != "" {
			producer, present := earlier[ref]
			if !present || !singleMixedTarget(producer, allowed) {
				return semanticInvalid()
			}
		}
		earlier[text(step["step_id"])] = text(transition["transition_kind"])
	}
	return nil
}
func mixedScriptWindow(policy, step, transition map[string]any) error {
	if step["valid_from_order"] == nil {
		return nil
	}
	if modelLess(step["valid_from_order"], transition["valid_from_order"]) || modelLess(transition["valid_until_order"], step["valid_until_order"]) {
		return semanticInvalid()
	}
	for _, field := range []string{"from_state_ref", "to_state_ref"} {
		state := object(object(policy["controller_states"])[text(transition[field])])
		if !mixedWindowsOverlap(step, state) {
			return semanticInvalid()
		}
	}
	return nil
}
func singleMixedTarget(producer string, allowed map[string]bool) bool {
	produced := map[string]bool{controlTerm: true}
	switch producer {
	case proposalTerm:
		produced[proposalTerm] = true
	case "approval", "denial":
		produced[decisionTerm] = true
	}
	count := 0
	for target := range produced {
		if allowed[target] {
			count++
		}
	}
	return count == 1
}

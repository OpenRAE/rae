package admission

import "slices"

func outcomeReferences(v any, fields ...string) error {
	if !fieldsUnique(v, fields...) {
		return invalid()
	}
	for _, field := range fields {
		if slices.ContainsFunc(stringsOf(at(v, field)), sdlBlank) {
			return invalid()
		}
	}
	return nil
}

func outcomeSourceBinding(v any) error {
	for _, field := range []string{termSourceID, "ref", "interpretation_role"} {
		if sdlBlank(stringAt(v, field)) {
			return invalid()
		}
	}
	if err := outcomeReferences(v, "evidence_refs", "provenance_refs", "diagnostics"); err != nil {
		return err
	}
	switch stringAt(v, "source_layer") {
	case "participant_episode_status", "benchmark_milestone", "subtask", "gold_step", "human_assistance", "scaffold_variant", "cost_resource_telemetry", "privacy_redaction_result":
		return require(len(array(at(v, "provenance_refs"))) > 0)
	default:
		return nil
	}
}

func outcomeTargetBinding(v any) error {
	for _, field := range []string{"target_id", "ref", "relation"} {
		if sdlBlank(stringAt(v, field)) {
			return invalid()
		}
	}
	if at(v, "governance_ref") != nil && sdlBlank(stringAt(v, "governance_ref")) {
		return invalid()
	}
	if err := outcomeReferences(v, "evidence_refs", "limitations", "diagnostics"); err != nil {
		return err
	}
	return require(stringAt(v, "target_layer") != "reward_signal" || at(v, "governance_ref") != nil)
}

func outcomeInterpretation(v any) error {
	for _, field := range []string{"semantic_version", "observation_point_basis", "interpretation_basis"} {
		if sdlBlank(stringAt(v, field)) {
			return invalid()
		}
	}
	if err := outcomeReferences(v, "evidence_refs", "limitations", "diagnostics"); err != nil {
		return err
	}
	sources, targets := array(at(v, "source_bindings")), array(at(v, "target_bindings"))
	local := at(v, "local_outcome")
	if len(rowSet(sources, termSourceID)) != len(sources) || len(rowSet(targets, "target_id")) != len(targets) {
		return invalid()
	}
	if local == nil {
		return require(len(targets) > 0)
	}
	if stringAt(v, "semantic_version") != "2.0.0" {
		return invalid()
	}
	index := controlRows(sources, termSourceID)
	for _, criterion := range array(at(local, "criteria")) {
		if stringAt(index[stringAt(criterion, termSourceID)], "source_layer") != "participant_action_outcome" {
			return invalid()
		}
	}
	return nil
}

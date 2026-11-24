package admission

import "github.com/OpenRAE/rae/implementations/go/contract/validation"

func (e *Validator) evidenceOwnerRules() map[string]definition {
	rules := map[string]definition{
		"required-evidence-media-type-provable": {check: func(i validation.Invocation) error {
			return mediaDeclaration(stringAt(i.Instance, "output_contract"), stringsOf(at(i.Instance, "media_types")))
		}},
		"run-plan-evidence-requirement-relation-owner-valid": {check: func(i validation.Invocation) error {
			rows := at(i.Instance, "run_plan", "evidence_requirement_relations")
			scenario := at(i.Instance, "intended_scenario_ref")
			if len(array(rows)) > 0 && scenario == nil {
				return invalid()
			}
			return relationOwner(rows, kindRun, termAuthoringInput, at(i.Instance, "spec_id"), at(i.Instance, "spec_version"), scenario)
		}},
	}
	for _, kind := range []string{kindTask, kindRun, kindStudy} {
		rules[kind+"-evidence-requirement-relation-owner-valid"] = definition{check: func(i validation.Invocation) error {
			version := at(i.Instance, kind+"_version")
			if kind == kindStudy && at(i.Instance, "definition_ref") != nil {
				version = at(i.Instance, "definition_ref", fieldRefVersion)
			}
			scenarioField := "scenario_ref"
			if kind == kindRun {
				scenarioField = "scenario_snapshot_ref"
			}
			return relationOwner(at(i.Instance, "evidence_requirement_relations"), kind, kind, at(i.Instance, kind+"_id"), version, at(i.Instance, scenarioField))
		}}
	}
	return rules
}
func exactReference(a, b any) bool {
	for _, field := range []string{fieldRefKind, fieldRefID, fieldRefVersion, "ref_digest", "ref_path"} {
		if !equal(at(a, field), at(b, field)) {
			return false
		}
	}
	return true
}
func relationOwner(rows any, scope, kind string, id, version, scenario any) error {
	if !unique(rowIDs(rows, fieldRelationID)) {
		return invalid()
	}
	expected := map[string]any{fieldRefKind: kind, fieldRefID: id, fieldRefVersion: version}
	for _, relation := range array(rows) {
		if stringAt(relation, "scope") != scope || !exactReference(at(relation, "authority_ref"), expected) {
			return invalid()
		}
		if scenario == nil {
			continue
		}
		base := at(relation, "base_scenario_ref")
		if stringAt(scenario, fieldRefKind) == kindScenario {
			if !equal(at(base, fieldRefID), at(scenario, fieldRefID)) {
				return invalid()
			}
		} else if !exactReference(base, scenario) {
			return invalid()
		}
	}
	return nil
}

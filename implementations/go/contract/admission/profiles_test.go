package admission

import "testing"

func TestValidationProfileRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"validation-profile-catalog-reference-integrity", `{"strengths":[{"strength_id":"s","rank":1}],"subject_kinds":[{"subject_kind":"task"}],"gate_kinds":[{"gate_kind":"g"}],"limitation_categories":[{"limitation_category":"l"}],"profiles":[{"profile_id":"p","profile_version":"v1","intended_subject_kinds":["task"],"minimum_strength":"s","required_gate_kinds":["g"],"limitation_categories":["l"]}]}`, true},
		{"validation-profile-catalog-reference-integrity", `{"strengths":[{"strength_id":"s","rank":2}]}`, false},
		{"validation-profile-catalog-reference-integrity", `{"strengths":[{"strength_id":"s","rank":1}],"profiles":[{"minimum_strength":"missing"}]}`, false},
		{"validation-profile-catalog-reference-integrity", `{"profiles":[{"profile_id":"p","profile_version":"v1"},{"profile_id":"p","profile_version":"v1"}]}`, false},
		{"validation-basis-strength-ordering-valid", `{"achieved_strength":"structural","gate_results":[{"gate_kind":"syntax_validation","outcome":"passed"},{"gate_kind":"schema_validation","outcome":"passed"},{"gate_kind":"vocabulary_validation","outcome":"passed"}]}`, true},
		{"validation-basis-strength-ordering-valid", `{"achieved_strength":"semantic","gate_results":[{"gate_kind":"syntax_validation","outcome":"passed"},{"gate_kind":"schema_validation","outcome":"passed"},{"gate_kind":"vocabulary_validation","outcome":"passed"}]}`, false},
		{"task-validation-basis-disclosure-identity-matches", `{"task_id":"t","task_version":"v1","validation_basis_disclosures":[{"subject_kind":"experiment_task","subject_ref":{"ref_id":"t","ref_version":"v1"}}]}`, true},
		{"task-validation-basis-disclosure-identity-matches", `{"task_id":"t","task_version":"v1","validation_basis_disclosures":[{"subject_kind":"experiment_task","subject_ref":{"ref_id":"other","ref_version":"v1"}}]}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

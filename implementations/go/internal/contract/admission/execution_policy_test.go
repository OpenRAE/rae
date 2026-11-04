package admission

import "testing"

func TestExecutionPolicyRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"execution-policy-executionpolicy", `{"response":"terminate"}`, true},
		{"execution-policy-executionpolicy", `{"response":"retry"}`, false},
		{"execution-policy-executionpolicy", `{"response":"retry","retry":{"max_attempts":2,"after_effect_policy":"idempotent"},"budget_ms":100,"delay_ms":10,"effect_classes":["applied"],"evidence_refs":["e"]}`, true},
		{"execution-policy-executionpolicy", `{"response":"retry","retry":{"max_attempts":2,"after_effect_policy":"disallow"},"budget_ms":100,"effect_classes":["applied"],"evidence_refs":["e"]}`, false},
		{"execution-policy-executionpolicy", `{"response":"terminate","clock_basis":"semantic"}`, false},
		{"execution-policy-executionpolicy", `{"response":"new-trial","fresh_trial_limit":1,"evidence_refs":["e"]}`, true},
		{"execution-policy-executionpolicydocument", `{"default":{"response":"terminate"},"scopes":[{"namespace":["n"],"scope":"","policy":{"response":"terminate"}}]}`, true},
		{"execution-policy-executionpolicydocument", `{"default":{"response":"terminate"},"scopes":[{"namespace":[],"scope":"","policy":{"response":"terminate"}}]}`, false},
		{"execution-policy-executionpolicycapabilities", `{"responses":["terminate","retry"]}`, true},
		{"execution-policy-executionpolicycapabilities", `{"responses":["resume"]}`, false},
		{"execution-policy-effectiveexecutionpolicy", `{"namespace":["n"],"governing_scope":"n#/workflows/w","scope":"/workflows/w/steps/s","retry_unit":"workflow-step","policy":{"response":"terminate","evidence_refs":["e"]},"evidence_requirements":{"e":{}}}`, true},
		{"execution-policy-effectiveexecutionpolicy", `{"namespace":["n"],"governing_scope":"n#/other","scope":"/workflows/w","policy":{"response":"terminate"}}`, false},
		{"execution-policy-planoperationmodel", `{"execution_policy_scopes":[{"governing_scope":"#","scope":"/a","policy":{"response":"terminate"}},{"governing_scope":"#","scope":"/a","policy":{"response":"terminate"}}]}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

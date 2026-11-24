package admission

import "testing"

func TestArtifactRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"exact-source-artifact-id-match", `{"source":{"name":"a","artifact_requirement":{"explicitness":"exact","exact_artifact":{"artifact_id":"a"}}}}`, true},
		{"exact-source-artifact-id-match", `{"source":{"name":"a","artifact_requirement":{"explicitness":"exact","exact_artifact":{"artifact_id":"b"}}}}`, false},
		{"exact-source-version-match", `{"source":{"artifact_requirement":{"explicitness":"exact","exact_artifact":{"version":"*"}}}}`, true},
		{"exact-source-version-match", `{"source":{"version":"1","artifact_requirement":{"explicitness":"exact","exact_artifact":{"version":"2"}}}}`, false},
		{"materialization-locked-input-join", `{"source":{"artifact_requirement":{"locked_inputs":[{"input_id":"a"}],"materialization_specifications":[{"profile":{"mechanism":"x-custom"},"locked_input_ids":["a"]}]}}}`, true},
		{"materialization-locked-input-join", `{"source":{"artifact_requirement":{"materialization_specifications":[{"profile":{"mechanism":"pull"}}]}}}`, false},
		{"materialization-locked-input-join", `{"source":{"artifact_requirement":{"materialization_specifications":[{"profile":{"mechanism":"materialization-specification"},"locked_input_ids":["missing"]}]}}}`, false},
		{"artifact-transformation-all-or-none", `{"status":"success","target_digest":"sha256:x","preservation":{"outcome":"verified"}}`, true},
		{"artifact-transformation-all-or-none", `{"status":"success","target_digest":"sha256:x","preservation":{"outcome":"failed"}}`, false},
		{"artifact-transformation-all-or-none", `{"status":"refused","diagnostics":[{}]}`, true},
		{"artifact-transformation-all-or-none", `{"status":"refused","diagnostics":[]}`, false},
		{"artifact-transformation-deterministic-order", `{"affected_identities":["a","b"],"preservation":{"outcome":"verified","evidence_digests":["a"]}}`, true},
		{"artifact-transformation-deterministic-order", `{"affected_identities":["b","a"]}`, false},
		{"artifact-transformation-deterministic-order", `{"preservation":{"outcome":"verified"}}`, false},
		{"artifact-transformation-deterministic-order", `{"preconditions":[{"check_id":"a","diagnostic_codes":["z","a"]}]}`, false},
		{"artifact-transformation-deterministic-order", `{"identity_map":[{"before":"b","after":"a"},{"before":"a","after":"z"}]}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

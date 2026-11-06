package admission

import "testing"

func TestExternalConceptRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"external-concept-source-locator-safe", `{"source_locator":"https://example.org/catalog"}`, true},
		{"external-concept-source-locator-safe", `{"source_locator":"https://user:pass@example.org/"}`, false},
		{"external-concept-source-locator-safe", `{"source_locator":"data:text/plain,hi"}`, false},
		{"external-concept-source-locator-safe", `{"source_locator":"https://example.org/?token=secret"}`, false},
		{"external-concept-source-pinned", `{"source_digest":"sha256:x"}`, true},
		{"external-concept-source-pinned", `{}`, false},
		{"external-concept-participants-unique", `{"participant_refs":["a","b"]}`, true},
		{"external-concept-participants-unique", `{"participant_refs":["a","a"]}`, false},
		{"external-concept-confidence-calibrated", `{"score":0,"calibration_profile_ref":{}}`, true},
		{"external-concept-confidence-calibrated", `{"score":0}`, false},
		{"external-concept-approximation-loss-consistent", `{"posture":"exact"}`, true},
		{"external-concept-approximation-loss-consistent", `{"posture":"exact","loss_details":["loss"]}`, false},
		{"external-concept-review-evidence-consistent", `{"status":"accepted","review_refs":[{}]}`, true},
		{"external-concept-review-evidence-consistent", `{"status":"unreviewed","review_refs":[{}]}`, false},
		{"external-concept-review-evidence-consistent", `{"status":"rejected"}`, false},
		{"external-concept-binding-identities", `{"bindings":{"a":{"binding_id":"a","subject":{"canonical_ref":"one"}},"b":{"binding_id":"b","subject":{"canonical_ref":"two"}}}}`, true},
		{"external-concept-binding-identities", `{"bindings":{"a":{"binding_id":"a"},"b":{"binding_id":"b"}}}`, false},
		{"external-concept-binding-identities", `{"bindings":{"a":{"binding_id":"b"}}}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

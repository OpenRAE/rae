package admission

import "testing"

func TestParticipantLocalRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"participant-control-occurrence-v2-acting-controller", `{"actor_ref":"a","occurrence":{"disposition":"accepted","controller_ref":"a"}}`, true},
		{"participant-control-occurrence-v2-acting-controller", `{"actor_ref":"a","occurrence":{"disposition":"rejected","attempted":{"controller_ref":"b"}}}`, false},
		{"participant-control-occurrence-v2-revision-advance", `{"occurrence":{"disposition":"accepted","expected_state_revision":9007199254740993,"resulting_state_revision":9007199254740994}}`, true},
		{"participant-control-occurrence-v2-revision-advance", `{"occurrence":{"disposition":"accepted","expected_state_revision":2,"resulting_state_revision":2}}`, false},
		{"participant-control-occurrence-v2-history-head", `{"occurrence":{"disposition":"accepted","expected_history_head":0,"occurrence_revision":1}}`, true},
		{"participant-control-occurrence-v2-history-head", `{"occurrence":{"disposition":"accepted","expected_history_head":1,"occurrence_revision":1}}`, false},
		{"participant-control-occurrence-v2-validity-bounds", `{"occurrence":{"disposition":"accepted","valid_from_order":1,"effective_order":1,"valid_until_order":1}}`, true},
		{"participant-control-occurrence-v2-validity-bounds", `{"occurrence":{"disposition":"accepted","valid_from_order":1,"effective_order":3,"valid_until_order":2}}`, false},
		{"context-view-sem216-archival-source-mediated", `{"audience_scope":"participant_visible","derivation_basis_ref":"basis","redaction_policy_ref":"redact","source_layers":[{"source_id":"a","source_layer":"derived_measure"}],"transformation":{"input_source_ids":["a"]}}`, true},
		{"context-view-sem216-archival-source-mediated", `{"audience_scope":"participant_visible","derivation_basis_ref":"basis","redaction_policy_ref":"redact","source_layers":[{"source_id":"a","source_layer":"derived_measure"}],"transformation":{"input_source_ids":[]}}`, false},
		{"context-view-sem216-payload-not-raw-archival", `{"audience_scope":"participant_visible","source_layers":[{"source_layer":"evidence_record","ref":"raw","evidence_refs":["also-raw"]}],"payload_ref":"view"}`, true},
		{"context-view-sem216-payload-not-raw-archival", `{"audience_scope":"participant_visible","source_layers":[{"source_layer":"evidence_record","ref":"raw","evidence_refs":["also-raw"]}],"payload_ref":"also-raw"}`, false},
		{"manifest-reference-digest-scope-valid", `{"ref_id":"p","ref_version":"processor-manifest/v2","ref_digest":"sha256:x","subject_ref":{"ref_kind":"processor","ref_id":"p"}}`, true},
		{"manifest-reference-digest-scope-valid", `{"ref_id":"p","ref_version":"processor-manifest/v2","ref_digest":"sha256:x","subject_ref":{"ref_kind":"processor","ref_id":"other"}}`, false},
		{"manifest-reference-digest-scope-valid", `{"ref_path":"/x"}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

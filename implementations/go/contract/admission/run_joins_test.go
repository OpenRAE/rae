package admission

import "testing"

func TestRunJoinRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"result-evidence-ref-resolves", `{"evidence_artifacts":[{"artifact_id":"a"}],"result_summaries":{"x":{"evidence_refs":[{"ref_id":"a"}]}}}`, true},
		{"result-evidence-ref-resolves", `{"evidence_artifacts":[],"result_summaries":{"x":{"evidence_refs":[{"ref_id":"a"}]}}}`, false},
		{"realized-form-evidence-refs-traced", `{"traceability":{"evidence_record_refs":[{"ref_id":"a","ref_digest":"SHA"}]},"realized_form_disclosures":[{"evidence_refs":[{"ref_id":"a","ref_digest":"sha"}]}]}`, true},
		{"realized-form-evidence-refs-traced", `{"realized_form_disclosures":[{"evidence_refs":[{"ref_id":"a"}]}]}`, false},
		{"augmentation-disclosure-evidence-refs-traced", `{"augmentation_disclosures":[{"augmentation_id":"a"},{"augmentation_id":"a"}]}`, false},
		{"participant-implementation-provenance-resolves", `{"run_id":"r","apparatus_context":{"components":{"p":{"component_kind":"participant-implementation","identity":{"name":"p","version":"1"}}}},"participant_implementation_provenance":{"run_id":"r","participant_implementations":[{"implementation_identity":{"name":"p","version":"1"}}]}}`, true},
		{"participant-implementation-provenance-resolves", `{"run_id":"r","apparatus_context":{"components":{"p":{"component_kind":"participant-implementation"}}}}`, false},
		{"augmentation-disclosure-semantics-valid", `{"classifications":["apparatus_only"],"augmented_by_ref":{"ref_kind":"processor"}}`, true},
		{"augmentation-disclosure-semantics-valid", `{"classifications":["environment_visible"],"augmented_by_ref":{"ref_kind":"processor"},"evidence_refs":[{"ref_id":"e"}],"environment_effect":"disclosed","carrier_refs":[{"ref_kind":"run","ref_id":"r"}]}`, true},
		{"augmentation-disclosure-semantics-valid", `{"classifications":["environment_visible"],"augmented_by_ref":{"ref_kind":"processor"}}`, false},
		{"augmentation-disclosure-semantics-valid", `{"classifications":["participant_visible"],"augmented_by_ref":{"ref_kind":"backend"},"evidence_refs":[{}],"participant_visibility":"disclosed","markings":[]}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

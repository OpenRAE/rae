package admission

import "testing"

func TestRunProvenanceLocalJoins(t *testing.T) {
	for _, test := range []struct {
		rule, raw string
		valid     bool
	}{
		{"experiment-run-admitted-trial-provenance", `{"run_id":"run","scenario_snapshot_ref":{"ref_digest":"digest"}}`, true},
		{"experiment-run-admitted-trial-provenance", `{"run_id":"run","scenario_snapshot_ref":{"ref_digest":"digest"},"trial_provenance":{"admitted_run_id":"other","instantiated_scenario_digest":"digest"}}`, false},
		{"run-materialization-carriers-archived", `{"run_id":"run","augmentation_disclosures":[{"carrier_refs":[{"ref_kind":"materialization-attestation","ref_id":"missing"}]}]}`, false},
		{"adaptive-difficulty-run-provenance-valid", `{"run_id":"run","started_at":"2026-01-01T00:00:00Z","ended_at":"2026-01-01T00:01:00Z","difficulty_provenance":{"baseline_variant_id":"base","policy":{"condition":"fixed","baseline_variant_id":"base"},"design_ref":{"ref_kind":"authoring-input","ref_version":"1","ref_digest":"digest"},"comparison_disposition":"fixed-baseline","decisions":[],"interventions":[]}}`, true},
	} {
		assertRule(t, test.rule, test.raw, test.valid)
	}
}

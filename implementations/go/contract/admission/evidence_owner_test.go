package admission

import "testing"

func TestEvidenceRelationOwners(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"task-evidence-requirement-relation-owner-valid", `{"task_id":"t","task_version":"1","scenario_ref":{"ref_kind":"scenario","ref_id":"s"},"evidence_requirement_relations":[{"relation_id":"r","scope":"task","authority_ref":{"ref_kind":"task","ref_id":"t","ref_version":"1"},"base_scenario_ref":{"ref_kind":"scenario-snapshot","ref_id":"s","ref_version":"1","ref_digest":"d"}}]}`, true},
		{"task-evidence-requirement-relation-owner-valid", `{"task_id":"t","task_version":"1","evidence_requirement_relations":[{"relation_id":"r","scope":"run","authority_ref":{"ref_kind":"task","ref_id":"t","ref_version":"1"}}]}`, false},
		{"run-evidence-requirement-relation-owner-valid", `{"run_id":"r","run_version":"1","scenario_snapshot_ref":{"ref_kind":"scenario-snapshot","ref_id":"s","ref_version":"1","ref_digest":"d"},"evidence_requirement_relations":[{"relation_id":"rel","scope":"run","authority_ref":{"ref_kind":"run","ref_id":"r","ref_version":"1"},"base_scenario_ref":{"ref_kind":"scenario-snapshot","ref_id":"s","ref_version":"1","ref_digest":"other"}}]}`, false},
		{"run-plan-evidence-requirement-relation-owner-valid", `{"spec_id":"spec","spec_version":"1","run_plan":{"evidence_requirement_relations":[{"relation_id":"r","scope":"run","authority_ref":{"ref_kind":"authoring-input","ref_id":"spec","ref_version":"1"}}]}}`, false},
		{"study-evidence-requirement-relation-owner-valid", `{"study_id":"s","study_version":"2","definition_ref":{"ref_version":"1"},"evidence_requirement_relations":[{"relation_id":"r","scope":"study","authority_ref":{"ref_kind":"study","ref_id":"s","ref_version":"1"}}]}`, true},
		{"study-evidence-requirement-relation-owner-valid", `{"study_id":"s","study_version":"2","evidence_requirement_relations":[{"relation_id":"r","scope":"study","authority_ref":{"ref_kind":"study","ref_id":"s","ref_version":"1"}}]}`, false},
		{"required-evidence-media-type-provable", `{"media_types":["application/jsonl"]}`, true},
		{"required-evidence-media-type-provable", `{"output_contract":"experiment-evidence-record-v1","media_types":["application/jsonl"]}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

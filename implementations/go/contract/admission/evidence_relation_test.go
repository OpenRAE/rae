package admission

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type testEvidenceRelationContext struct {
	scenarios []EvidenceScenario
	captures  [][]byte
}

func (c testEvidenceRelationContext) EvidenceScenarios() []EvidenceScenario { return c.scenarios }
func (c testEvidenceRelationContext) CaptureSpecs() [][]byte                { return c.captures }

func TestEvidenceRelationResolvesExactOwnerArtifacts(t *testing.T) {
	e := boundTestOwner(t)
	source := []byte(`{"name":"exp731-scenario","version":"1.0.0","evidence_requirements":{"event-log":{"description":"Capture event fields.","source_class":"external","scope":"run","window":"run","channel":"log","artifact_role":"event-log","media_types":["application/json"],"sensitivity":"plain","redaction":"none","integrity":"checksum","retention":"run_lifetime","loss_disclosure":"best_effort","output_contract":"participant-behavior-history-event-stream-v1","field_selectors":["/0"]}}}`)
	admitted, err := e.low.Validate("sdl-authoring-input-v1", source, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	refDigest := "sha256:" + strings.Repeat("a", 64)
	relation := decodeRuleObject(t, `{"relation_id":"detail","relation_version":"1","relation_kind":"refine","scope":"task","authority_ref":{"ref_kind":"task","ref_id":"task","ref_version":"1"},"base_scenario_ref":{"ref_kind":"scenario-snapshot","ref_id":"exp731-scenario","ref_version":"1.0.0","ref_digest":"`+refDigest+`"},"base_requirement_address":"evidence_requirements.event-log","capture_spec_ref":{"ref_kind":"capture-spec","ref_id":"capture","ref_version":"1"},"capture_requirement_ref":"detail","refinement_dimensions":["field-selectors"],"rationale":"More fields."}`)
	capture := fixtureObject(t, "fixtures/experiment-core/experiment-capture-spec-v1/valid/reference.json")
	capture["capture_spec_id"], capture["spec_version"], capture["scope_refs"] = "capture", "1", []any{at(relation, "authority_ref")}
	window := stringAt(array(capture["capture_windows"])[0], "window_id")
	capture["capture_requirements"] = map[string]any{"detail": map[string]any{"requirement_id": "detail", "title": "Detail", "capture_kind": "log", "capture_scope": "run", "channel_ref": map[string]any{"ref_kind": "measurement-channel", "ref_id": "log", "ref_version": "1"}, "window_refs": []any{window}, "expected_media_types": []any{"application/json"}, "required_artifact_roles": []any{"event-log"}, "output_contract": "participant-behavior-history-event-stream-v1", "field_selectors": []any{"/0", "/0/action_contract_address"}, "sensitivity": "internal", "integrity_requirements": []any{"checksum", "sha256-digest"}, "loss_disclosure_required": true}}
	raw, err := json.Marshal(capture)
	if err != nil {
		t.Fatal(err)
	}
	context := testEvidenceRelationContext{scenarios: []EvidenceScenario{{Value: admitted, Digest: refDigest}}, captures: [][]byte{raw}}
	if err := e.evidenceRelation(validation.Invocation{Instance: relation, Context: context}); err != nil {
		t.Fatal(err)
	}
	context.scenarios = append(context.scenarios, context.scenarios[0])
	if err := e.evidenceRelation(validation.Invocation{Instance: relation, Context: context}); err == nil {
		t.Error("accepted ambiguous authored scenario")
	}
}

func TestEvidenceRefinementPreservesEverySelectedDimension(t *testing.T) {
	base := decodeRuleObject(t, `{"field_selectors":["/base"],"artifact_role":"event-log","integrity":"checksum","loss_disclosure":"required"}`)
	for _, test := range []struct {
		dimension, scoped string
		strict, valid     bool
	}{
		{"field-selectors", `{"field_selectors":["/base","/detail"]}`, true, true},
		{"field-selectors", `{"field_selectors":["/detail"]}`, false, false},
		{"artifact-roles", `{"required_artifact_roles":["event-log"]}`, false, true},
		{"artifact-roles", `{"required_artifact_roles":["event-log","other"]}`, false, false},
		{"integrity-requirements", `{"integrity_requirements":["checksum","sha256-digest"]}`, true, true},
		{"integrity-requirements", `{"integrity_requirements":["sha256-digest"]}`, false, false},
		{"loss-disclosure", `{"loss_disclosure_required":true}`, false, true},
		{"loss-disclosure", `{"loss_disclosure_required":false}`, false, false},
	} {
		strict, err := refinementDimension(test.dimension, base, decodeRuleObject(t, test.scoped))
		if (err == nil) != test.valid || err == nil && strict != test.strict {
			t.Errorf("%s: strict=%v err=%v", test.dimension, strict, err)
		}
	}
}

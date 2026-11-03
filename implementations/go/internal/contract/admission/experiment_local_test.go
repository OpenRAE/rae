package admission

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func assertRule(t *testing.T, id, raw string, valid bool) {
	t.Helper()
	e, err := newCatalogOwner()
	if err != nil {
		t.Fatal(err)
	}
	instance := decodeRuleObject(t, raw)
	rule, ok := e.checker(id)
	if !ok {
		t.Fatalf("checker(%s) missing", id)
	}
	checkErr := rule.check(validation.Invocation{Key: validation.Key{InvariantID: id}, Root: instance, Instance: instance})
	if (checkErr == nil) != valid {
		t.Errorf("%s(%s) = %v, want valid=%v", id, raw, checkErr, valid)
	}
}

func decodeRuleObject(t *testing.T, raw string) any {
	t.Helper()
	decoder := json.NewDecoder(bytes.NewBufferString(raw))
	decoder.UseNumber()
	var instance any
	if err := decoder.Decode(&instance); err != nil {
		t.Fatal(err)
	}
	return instance
}

func TestExperimentLocalRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"capture-window-interval-valid", `{"starts_at":"2026-01-01T00:00:00Z","ends_at":"2026-01-01T01:00:00+01:00"}`, true},
		{"capture-window-interval-valid", `{"starts_at":"2026-01-01T00:00:00Z","ends_at":"2025-12-31T23:59:59Z"}`, false},
		{"derived-measure-generated-at-valid", `{"generated_at":"2026-02-30T00:00:00Z"}`, false},
		{"derived-measure-generated-at-valid", `{"generated_at":"2016-12-31T23:59:60Z"}`, true},
		{"derived-measure-reported-value-present", `{"value_status":"reported","value":false}`, true},
		{"derived-measure-reported-value-present", `{"value_status":"reported","value":null}`, false},
		{"derived-measure-reported-value-present", `{"value_status":"withheld","value":0}`, false},
		{"capture-requirement-key-matches-requirement-id", `{"capture_windows":[{"window_id":"w"}],"capture_requirements":{"r":{"requirement_id":"r","window_refs":["w"]}}}`, true},
		{"capture-requirement-key-matches-requirement-id", `{"capture_windows":[{"window_id":"w"},{"window_id":"w"}],"capture_requirements":{}}`, false},
		{"capture-requirement-key-matches-requirement-id", `{"capture_windows":[{"window_id":"w"}],"capture_requirements":{"r":{"requirement_id":"r","window_refs":["missing"]}}}`, false},
		{"metric-definition-key-matches-metric-id", `{"metric_definitions":{"a":{"metric_id":"a"}}}`, true},
		{"metric-definition-key-matches-metric-id", `{"metric_definitions":{"a":{"metric_id":"b"}}}`, false},
		{"evidence-record-raw-content-present", `{"redaction_state":"none","raw_content":{"payload_summary":"bounded"}}`, true},
		{"evidence-record-raw-content-present", `{"redaction_state":"withheld","redaction_policy":"p","raw_content":{"payload_summary":"bounded"}}`, false},
		{"evidence-record-raw-content-present", `{"redaction_state":"none","raw_content":{"content_uri":"urn:x"}}`, false},
		{"trial-replacement-policy-explicit-and-bounded", `{"max_replacements":0,"replace_on":[]}`, true},
		{"trial-replacement-policy-explicit-and-bounded", `{"max_replacements":1,"replace_on":[]}`, false},
		{"trial-replacement-policy-explicit-and-bounded", `{"max_replacements":1,"replace_on":["failed","failed"]}`, false},
		{"analysis-plan-substantive-methods-required", `{"metrics":["a"],"primary_metric":"b"}`, false},
		{"capture-media-type-provable", `{"output_contract":"experiment-evidence-record-v1","expected_media_types":["application/json"]}`, true},
		{"capture-media-type-provable", `{"output_contract":"experiment-evidence-record-v1","expected_media_types":["application/jsonl"]}`, false},
		{"capture-media-type-provable", `{"output_contract":"participant-behavior-history-event-stream-v1","expected_media_types":["application/jsonl"]}`, true},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

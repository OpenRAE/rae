package admission

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestScalarFamilyRules(t *testing.T) {
	e, err := newCatalogOwner()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"random-stream-profile-transform-keys-match", `{"transforms":{"a":{"transform_id":"a"}}}`, true},
		{"random-stream-profile-transform-keys-match", `{"transforms":{"a":{"transform_id":"b"}}}`, false},
		{"random-stream-address-draw-purpose-governed", `{"draw_purpose":"agent-policy"}`, true},
		{"random-stream-address-draw-purpose-governed", `{"draw_purpose":"invented"}`, false},
		{"participant-random-stream-address-governed", `{"draw_purpose":"agent-policy","policy_address":"participant.autonomous-execution.red","participant_address":"participant.behavior.red"}`, true},
		{"participant-random-stream-address-governed", `{"draw_purpose":"agent-policy","policy_address":"policies.red","participant_address":"participant.behavior.red"}`, false},
		{"random-stream-draw-record-local-coordinate-matches-address", `{"local_coordinate":1.0,"address":{"local_coordinate":1}}`, true},
		{"random-stream-draw-record-local-coordinate-matches-address", `{"local_coordinate":2,"address":{"local_coordinate":1}}`, false},
		{"random-stream-draw-record-outcome-matches-exhaustion", `{"rejection_exhausted":true}`, true},
		{"random-stream-draw-record-outcome-matches-exhaustion", `{"rejection_exhausted":false,"outcome":{"value":0}}`, true},
		{"random-stream-draw-record-outcome-matches-exhaustion", `{"rejection_exhausted":true,"outcome":{"value":0}}`, false},
		{"random-stream-draw-record-outcome-matches-exhaustion", `{}`, false},
		{"unique-sentinel-decision-pointers", `{"sentinel_decisions":[{"pointer":"/a"},{"pointer":"/b"}]}`, true},
		{"unique-sentinel-decision-pointers", `{"sentinel_decisions":[{"pointer":"/a"},{"pointer":"/a"}]}`, false},
	} {
		decoder := json.NewDecoder(bytes.NewBufferString(test.raw))
		decoder.UseNumber()
		var value any
		if err := decoder.Decode(&value); err != nil {
			t.Fatal(err)
		}
		rule, ok := e.checker(test.id)
		if !ok {
			t.Fatalf("checker(%s) missing", test.id)
		}
		checkErr := rule.check(validation.Invocation{Key: validation.Key{InvariantID: test.id}, Root: value, Instance: value})
		if (checkErr == nil) != test.valid {
			t.Errorf("%s(%s) = %v, want valid=%v", test.id, test.raw, checkErr, test.valid)
		}
	}
}

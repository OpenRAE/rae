package validation

import (
	"encoding/json"
	"io/fs"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

// TestPublishedTypesEnforceMaintainerDecision protects the explicit decision
// recorded for issue #1780: Go requires the published types without Python's
// implicit conversions, while integral JSON numbers remain integers.
func TestPublishedTypesEnforceMaintainerDecision(t *testing.T) {
	v, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	source, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		id, path string
		member   []string
		value    string
		valid    bool
	}{
		{"random-stream-profile-v1", "fixtures/profiles/random-stream-profile-v1/valid/blake3-xof-v1.json", []string{"root_entropy", "byte_length"}, `"32"`, false},
		{"random-stream-profile-v1", "fixtures/profiles/random-stream-profile-v1/valid/blake3-xof-v1.json", []string{"root_entropy", "byte_length"}, `true`, false},
		{"random-stream-profile-v1", "fixtures/profiles/random-stream-profile-v1/valid/blake3-xof-v1.json", []string{"root_entropy", "byte_length"}, `32.0`, true},
		{"participant-execution-service-state-v1", "fixtures/participant-runtime/participant-execution-service-state-v1/valid/running-ready.json", []string{"capacity"}, `"4"`, false},
		{"participant-execution-service-state-v1", "fixtures/participant-runtime/participant-execution-service-state-v1/valid/running-ready.json", []string{"capacity"}, `true`, false},
		{"participant-execution-service-state-v1", "fixtures/participant-runtime/participant-execution-service-state-v1/valid/running-ready.json", []string{"capacity"}, `4.0`, true},
		{"operation-receipt-v1", "fixtures/control-plane/operation-receipt-v1/valid/accepted.json", []string{"accepted"}, `"true"`, false},
		{"operation-receipt-v1", "fixtures/control-plane/operation-receipt-v1/valid/accepted.json", []string{"accepted"}, `1`, false},
	} {
		data, readErr := fs.ReadFile(source, test.path)
		if readErr != nil {
			t.Fatal(readErr)
		}
		modified := replaceMember(t, data, test.member, json.RawMessage(test.value))
		checkErr := v.CheckSchema(test.id, modified, ingress.Limits{MaxBytes: 4194304, MaxDepth: 64})
		if (checkErr == nil) != test.valid {
			t.Errorf("CheckSchema(%s,%v=%s) = %v, want valid=%v", test.id, test.member, test.value, checkErr, test.valid)
		}
	}
}

func replaceMember(t *testing.T, data []byte, path []string, value json.RawMessage) []byte {
	t.Helper()
	var root map[string]any
	if err := json.Unmarshal(data, &root); err != nil {
		t.Fatal(err)
	}
	current := root
	for _, name := range path[:len(path)-1] {
		child, ok := current[name].(map[string]any)
		if !ok {
			t.Fatalf("fixture member %s is not an object", name)
		}
		current = child
	}
	current[path[len(path)-1]] = value
	modified, err := json.Marshal(root)
	if err != nil {
		t.Fatal(err)
	}
	return modified
}

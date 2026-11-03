package binding

import (
	"encoding/json"
	"io/fs"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

// TestGeneratedRegistry exercises every generated constructor in CI. It checks
// transport mechanics only; schema and semantic admission belong to validation.
func TestGeneratedRegistry(t *testing.T) {
	source, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	entries, err := fs.ReadDir(source, "schema-publication/entries")
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		id := strings.TrimSuffix(entry.Name(), ".json")
		if _, err := Decode(id, []byte(`{`)); err == nil {
			t.Errorf("Decode(%s,malformed) = nil, want refusal", id)
		}
		raw := []byte(`{}`)
		transport, decodeErr := Decode(id, raw)
		if decodeErr != nil {
			raw = []byte(`[]`)
			transport, decodeErr = Decode(id, raw)
		}
		if decodeErr != nil {
			t.Errorf("Decode(%s,empty transport) = %v", id, decodeErr)
			continue
		}
		encoded, marshalErr := json.Marshal(transport)
		if marshalErr != nil || string(encoded) != string(raw) {
			t.Errorf("Marshal(%s) = %s, error=%v, want %s", id, encoded, marshalErr, raw)
		}
	}
	if _, err := Decode("unknown", []byte(`{}`)); err == nil {
		t.Error("Decode(unknown) = nil, want refusal")
	}
}

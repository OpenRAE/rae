package validation

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// Exact vectors from source issue tests retain their published schema pointers.
// Primitive fields use the production compiled schema; object fragments also
// exercise the bounded public context-fragment entry point.
func TestPublishedIdentityAndMixedControlDefects(t *testing.T) {
	cases := loadSchemaDefectCases(t)
	v, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	for index, c := range cases {
		t.Run(fmt.Sprintf("%s/%s/%s/%d", c.Source, c.Contract, c.Case, index), func(t *testing.T) {
			checkSchemaDefect(t, v, c)
		})
	}
}

type schemaDefectCase struct {
	Source   string          `json:"source"`
	Case     string          `json:"case"`
	Contract string          `json:"contract_id"`
	Pointer  string          `json:"pointer"`
	Payload  json.RawMessage `json:"payload"`
	Valid    bool            `json:"valid"`
}

func checkSchemaDefect(t *testing.T, v *Validator, c schemaDefectCase) {
	t.Helper()
	schema := findSchemaFragment(v.contracts[c.Contract], c.Pointer)
	if schema == nil {
		t.Fatal("published fragment missing", c.Pointer)
	}
	var payload any
	decoder := json.NewDecoder(bytes.NewReader(c.Payload))
	decoder.UseNumber()
	err := decoder.Decode(&payload)
	if err != nil {
		t.Fatal(err)
	}
	if err := schema.Validate(payload); (err == nil) != c.Valid {
		t.Fatalf("schema result differs from Python: %v", err)
	}
	if _, ok := payload.(map[string]any); ok {
		_, err := v.DecodeObjectFragment(c.Contract, c.Pointer, c.Payload, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64})
		if (err == nil) != c.Valid {
			t.Fatalf("public fragment result differs from Python: %v", err)
		}
	}
}

func loadSchemaDefectCases(t *testing.T) []schemaDefectCase {
	t.Helper()
	raw, err := os.ReadFile("testdata/schema-defect-verdicts.json")
	if err != nil {
		t.Fatal(err)
	}
	var recording struct {
		CaseFiles []string `json:"case_files"`
	}
	if err := json.Unmarshal(raw, &recording); err != nil {
		t.Fatal(err)
	}
	if len(recording.CaseFiles) != 5 {
		t.Fatal("source defect shard inventory changed")
	}
	var cases []schemaDefectCase
	for index, path := range recording.CaseFiles {
		if path != fmt.Sprintf("schema-defect-cases-%02d.json", index+1) {
			t.Fatal("unsafe reference shard path")
		}
		raw, err := fs.ReadFile(os.DirFS("testdata"), path)
		if err != nil {
			t.Fatal(err)
		}
		var shard []schemaDefectCase
		if err := json.Unmarshal(raw, &shard); err != nil {
			t.Fatal(err)
		}
		if len(shard) != 153 {
			t.Fatal("source defect shard changed")
		}
		cases = append(cases, shard...)
	}
	return cases
}

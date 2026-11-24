package authoring

import (
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type migrationReference struct {
	Name        string          `json:"name"`
	Source      string          `json:"source"`
	SourceBytes []byte          `json:"source_bytes"`
	Context     json.RawMessage `json:"context"`
	Output      json.RawMessage `json:"output"`
	Result      json.RawMessage `json:"result"`
}

func TestMigrationReference(t *testing.T) {
	raw, err := readCompressedFixture("testdata/migrations.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []migrationReference `json:"cases"`
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	parser := operationParser(t)
	for _, row := range fixture.Cases {
		t.Run(row.Name, func(t *testing.T) {
			input := row.SourceBytes
			if input == nil {
				input = []byte(row.Source)
			}
			result, envelope, err := parser.Migrate(input, row.Context)
			if err != nil {
				t.Fatal(err)
			}
			assertOperationReference(t, result, envelope, row.Output, row.Result)
		})
	}
}

func assertOperationReference(t *testing.T, result *Document, envelope, output, report []byte) {
	t.Helper()
	assertJSONReference(t, "result", envelope, report)
	actual := []byte("null")
	if result != nil {
		if !result.Validated() {
			t.Fatal("output was not admitted")
		}
		actual = result.JSON()
	}
	assertJSONReference(t, "output", actual, output)
}
func assertJSONReference(t *testing.T, label string, actual, expected []byte) {
	t.Helper()
	var got, want any
	if err := json.Unmarshal(actual, &got); err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(expected, &want); err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("%s differs (-want +got):\n%s", label, diff)
	}
}

package authoring

import (
	"encoding/json"
	"errors"
	"os"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type safeStateVector struct {
	Name       string            `json:"name"`
	Files      map[string]string `json:"files"`
	Accepted   bool              `json:"accepted"`
	Errors     []string          `json:"errors"`
	SafeStates json.RawMessage   `json:"safe_states"`
	Rename     map[string]any    `json:"rename"`
	Renamed    json.RawMessage   `json:"renamed"`
}

// TestSafeStateReference pins resolution, validation, import rewriting and
// rename rewriting to the reference owner.
func TestSafeStateReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/safe-state-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors struct {
		Cases []safeStateVector `json:"cases"`
	}
	if err = json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, vector := range vectors.Cases {
		t.Run(vector.Name, func(t *testing.T) { vector.run(t, parser) })
	}
}

func (vector safeStateVector) run(t *testing.T, parser *Parser) {
	t.Helper()
	files := fstest.MapFS{}
	for name, text := range vector.Files {
		files[name] = &fstest.MapFile{Data: []byte(text)}
	}
	document, err := parser.Decode(Request{Source: []byte(vector.Files["main.yaml"]), Name: "main.yaml", FS: files})
	if err != nil {
		t.Fatal(err)
	}
	admitted, _, err := parser.Validate(document)
	if !vector.Accepted {
		vector.checkRefusal(t, err)
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	states, err := admitted.SafeStates()
	if string(vector.SafeStates) == "null" {
		if err == nil {
			t.Fatal("deferred safe-state references resolved before instantiation")
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	assertJSONEqual(t, vector.SafeStates, states)
	if vector.Rename != nil {
		vector.checkRename(t, parser, admitted)
	}
}

func (vector safeStateVector) checkRefusal(t *testing.T, err error) {
	t.Helper()
	var refusal diagnostic.Error
	if !errors.As(err, &refusal) {
		t.Fatalf("validation = %v; want refusal %v", err, vector.Errors)
	}
	messages := []string{}
	for _, finding := range refusal.Diagnostics() {
		messages = append(messages, finding.Message)
	}
	if diff := cmp.Diff(vector.Errors, messages); diff != "" {
		t.Fatalf("refusal differs from reference (-want +got):\n%s", diff)
	}
}

func (vector safeStateVector) checkRename(t *testing.T, parser *Parser, admitted *Document) {
	t.Helper()
	request, err := json.Marshal(map[string]any{"operation_profile": "rename-sdl-declaration/v1", "request": vector.Rename, "policy": map[string]any{"allowed_loss_kinds": []any{}}, "binding_documents": []any{}})
	if err != nil {
		t.Fatal(err)
	}
	renamed, _, err := parser.Transform(admitted, request)
	if err != nil || renamed == nil {
		t.Fatalf("rename = %v, %v; want the reference output", renamed, err)
	}
	var output map[string]any
	if err = json.Unmarshal(renamed.JSON(), &output); err != nil {
		t.Fatal(err)
	}
	assertJSONEqual(t, vector.Renamed, output[safeStateSection])
}

func assertJSONEqual(t *testing.T, want json.RawMessage, value any) {
	t.Helper()
	got, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	var expected, actual any
	if json.Unmarshal(want, &expected) != nil || json.Unmarshal(got, &actual) != nil {
		t.Fatal("reference JSON is invalid")
	}
	if diff := cmp.Diff(expected, actual); diff != "" {
		t.Errorf("value differs from reference (-want +got):\n%s", diff)
	}
}

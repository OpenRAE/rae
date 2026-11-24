package authoring

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type transformationReference struct {
	Name    string            `json:"name"`
	Root    string            `json:"root"`
	Files   map[string]string `json:"files"`
	Request json.RawMessage   `json:"request"`
	Output  json.RawMessage   `json:"output"`
	Result  json.RawMessage   `json:"result"`
}

func TestTransformationReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/transformations.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors struct {
		Cases []transformationReference `json:"cases"`
	}
	if err = json.Unmarshal(raw, &vectors); err != nil {
		t.Fatal(err)
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, vector := range vectors.Cases {
		t.Run(vector.Name, func(t *testing.T) {
			vector.run(t, parser)
		})
	}
}

func (vector transformationReference) run(t *testing.T, parser *Parser) {
	t.Helper()
	document := vector.input(t, parser)
	before, err := document.CanonicalBytes()
	if err != nil {
		t.Fatal(err)
	}
	result, report, err := parser.Transform(document, vector.Request)
	if err != nil {
		t.Fatal(err)
	}
	assertOperationReference(t, result, report, vector.nativeOutput(t), vector.Result)
	after, err := document.CanonicalBytes()
	if err != nil || !bytes.Equal(before, after) {
		t.Fatal("transformation mutated its source")
	}
}

func (vector transformationReference) nativeOutput(t *testing.T) json.RawMessage {
	t.Helper()
	if vector.Name != "rename-composed-reference" {
		return vector.Output
	}
	// The frozen Python result retains these five obsolete declaration paths.
	// Correct only those expected values; compare every other reference field.
	// TestTransformationKeepsImportedProvenance locks downstream instantiation.
	corrections := map[string]string{
		"nodes.shared.primary":               "nodes.shared.frontend",
		"nodes.shared.primary.type":          "nodes.shared.frontend.type",
		"nodes.shared.primary.resources":     "nodes.shared.frontend.resources",
		"nodes.shared.primary.resources.ram": "nodes.shared.frontend.resources.ram",
		"nodes.shared.primary.resources.cpu": "nodes.shared.frontend.resources.cpu",
	}
	var expected map[string]any
	if err := json.Unmarshal(vector.Output, &expected); err != nil {
		t.Fatal(err)
	}
	for _, raw := range array(object(expected["expansion_provenance"])[termExplicitness]) {
		record := object(raw)
		before := text(record["model_path"])
		if after, present := corrections[before]; present {
			record["model_path"] = after
			delete(corrections, before)
		}
	}
	if len(corrections) != 0 {
		t.Fatal("the pinned Python provenance defect has changed")
	}
	output, err := json.Marshal(expected)
	if err != nil {
		t.Fatal(err)
	}
	return output
}
func (vector transformationReference) input(t *testing.T, parser *Parser) *Document {
	t.Helper()
	files := fstest.MapFS{}
	for name, text := range vector.Files {
		files[name] = &fstest.MapFile{Data: []byte(text)}
	}
	document, err := parser.Decode(Request{Source: []byte(vector.Files[vector.Root]), Name: vector.Root, FS: files})
	if err != nil {
		t.Fatal(err)
	}
	document, _, err = parser.Validate(document)
	if err != nil {
		t.Fatal(err)
	}
	return document
}
func TestTransformationRequestBound(t *testing.T) {
	limits := source.DefaultLimits()
	limits.MaxInputBytes = 128
	parser, err := New(limits)
	if err != nil {
		t.Fatal(err)
	}
	document, err := parser.Decode(Request{Source: []byte("name: root\nnodes: {n: {type: compute}}\n")})
	if err != nil {
		t.Fatal(err)
	}
	document, _, err = parser.Validate(document)
	if err != nil {
		t.Fatal(err)
	}
	request := append([]byte(`{"operation_profile":"rename-sdl-declaration/v1","request":{"target_address":"nodes.n","new_local_name":"m"}}`), bytes.Repeat([]byte{' '}, 128)...)
	if result, report, err := parser.Transform(document, request); err == nil || result != nil || report != nil {
		t.Fatal("oversized request reached transformation admission")
	}
}

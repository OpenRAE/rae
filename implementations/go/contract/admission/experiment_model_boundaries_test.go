package admission

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"os"
	"testing"
)

type experimentModelBoundaryDocument struct {
	ContractID string          `json:"contract_id"`
	Document   json.RawMessage `json:"document"`
}
type experimentModelBoundaryMutation struct {
	Name   string            `json:"name"`
	Base   int               `json:"base"`
	Path   []json.RawMessage `json:"path"`
	Delete bool              `json:"delete"`
	Value  json.RawMessage   `json:"value"`
}

func TestExperimentModelSemanticRefusalsMatchIndependentSource(t *testing.T) {
	file, err := os.Open("testdata/experiment-model-boundaries-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if closeErr := file.Close(); closeErr != nil {
			t.Error(closeErr)
		}
	}()
	stream, err := gzip.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if err := stream.Close(); err != nil {
			t.Error(err)
		}
	}()
	var reference struct {
		Documents []experimentModelBoundaryDocument `json:"documents"`
		Cases     []experimentModelBoundaryMutation `json:"cases"`
	}
	if err := json.NewDecoder(stream).Decode(&reference); err != nil {
		t.Fatal(err)
	}
	if len(reference.Documents) != 42 || len(reference.Cases) != 1862 {
		t.Fatal("model semantic refusal inventory changed")
	}
	owner := boundTestOwner(t)
	for _, document := range reference.Documents {
		if _, err := ExperimentModelProjection(owner, document.ContractID, document.Document); err != nil {
			t.Fatal("canonical source model refused", document.ContractID, err)
		}
	}
	for _, test := range reference.Cases {
		t.Run(test.Name, func(t *testing.T) { checkExperimentModelMutation(t, owner, reference.Documents[test.Base], test) })
	}
}
func checkExperimentModelMutation(t *testing.T, owner *Validator, base experimentModelBoundaryDocument, test experimentModelBoundaryMutation) {
	t.Helper()
	var document any
	decodeBoundaryJSON(t, base.Document, &document)
	target := document
	for _, part := range test.Path[:len(test.Path)-1] {
		target = modelMutationChild(t, target, part)
	}
	last := test.Path[len(test.Path)-1]
	var value any
	decodeBoundaryJSON(t, test.Value, &value)
	switch parent := target.(type) {
	case map[string]any:
		var key string
		decodeBoundaryJSON(t, last, &key)
		if test.Delete {
			delete(parent, key)
		} else {
			parent[key] = value
		}
	case []any:
		var index int
		decodeBoundaryJSON(t, last, &index)
		parent[index] = value
	default:
		t.Fatal("mutation parent is not a container")
	}
	raw, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ExperimentModelProjection(owner, base.ContractID, raw); err == nil {
		t.Fatal("source-refused semantic mutation admitted")
	}
}
func decodeBoundaryJSON(t *testing.T, raw []byte, target any) {
	t.Helper()
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(target); err != nil {
		t.Fatal(err)
	}
}
func modelMutationChild(t *testing.T, parent any, key json.RawMessage) any {
	t.Helper()
	switch value := parent.(type) {
	case map[string]any:
		var part string
		decodeBoundaryJSON(t, key, &part)
		return value[part]
	case []any:
		var index int
		decodeBoundaryJSON(t, key, &index)
		return value[index]
	default:
		t.Fatal("mutation path left source document")
		return nil
	}
}

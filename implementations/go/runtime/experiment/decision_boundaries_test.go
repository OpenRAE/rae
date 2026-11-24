package experiment

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
)

type decisionBoundaryDocument struct {
	Document json.RawMessage `json:"document"`
	ID       string          `json:"id"`
}
type decisionBoundaryMutation struct {
	Name   string          `json:"name"`
	Base   int             `json:"base"`
	Path   []string        `json:"path"`
	Delete bool            `json:"delete"`
	Value  json.RawMessage `json:"value"`
}
type decisionBoundaryReference struct {
	Documents []decisionBoundaryDocument `json:"documents"`
	Cases     []decisionBoundaryMutation `json:"cases"`
}

func TestDecisionFieldRefusalsMatchIndependentSourceModels(t *testing.T) {
	raw, err := os.ReadFile("testdata/decision-boundaries-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference decisionBoundaryReference
	if json.Unmarshal(raw, &reference) != nil || len(reference.Documents) != 16 || len(reference.Cases) != 481 {
		t.Fatal("decision field refusal inventory changed")
	}
	for _, baseline := range reference.Documents {
		checkCanonicalBoundaryDecision(t, baseline)
	}
	for _, test := range reference.Cases {
		t.Run(test.Name, func(t *testing.T) { checkDecisionFieldMutation(t, reference.Documents[test.Base].Document, test) })
	}
}
func checkCanonicalBoundaryDecision(t *testing.T, baseline decisionBoundaryDocument) {
	t.Helper()
	decision, err := DecodeDecision(baseline.Document)
	if err != nil {
		t.Fatal("canonical source record refused", err)
	}
	if decision.ID() != baseline.ID {
		t.Fatal("canonical source record identity changed")
	}
	actual, e1 := canonjson.JCS(decision.JSON())
	expected, e2 := canonjson.JCS(baseline.Document)
	if e1 != nil || e2 != nil || !bytes.Equal(actual, expected) {
		t.Fatal("canonical source record projection changed")
	}
}
func checkDecisionFieldMutation(t *testing.T, baseline json.RawMessage, test decisionBoundaryMutation) {
	t.Helper()
	var document map[string]any
	decoder := json.NewDecoder(bytes.NewReader(baseline))
	decoder.UseNumber()
	if decoder.Decode(&document) != nil {
		t.Fatal("decision input fixture")
	}
	target := document
	for _, part := range test.Path[:len(test.Path)-1] {
		target = object(target[part])
		if target == nil {
			t.Fatal("missing mutation parent")
		}
	}
	if test.Delete {
		delete(target, test.Path[len(test.Path)-1])
	} else {
		var value any
		decoder = json.NewDecoder(bytes.NewReader(test.Value))
		decoder.UseNumber()
		if decoder.Decode(&value) != nil {
			t.Fatal("mutation value fixture")
		}
		target[test.Path[len(test.Path)-1]] = value
	}
	changed, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := DecodeDecision(changed); err == nil {
		t.Fatal("source-refused private decision admitted")
	}
}

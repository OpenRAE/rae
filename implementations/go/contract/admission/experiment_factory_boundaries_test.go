package admission

import (
	"encoding/json"
	"testing"
)

func TestEveryDeclaredExperimentFactoryMatchesIndependentSourceDefaults(t *testing.T) {
	var reference struct {
		Factories map[string]json.RawMessage `json:"factories"`
	}
	readFullReferenceJSON(t, "testdata/experiment-factories-reference.json", &reference)
	if len(reference.Factories) != 63 {
		t.Fatal("factory inventory changed")
	}
	for model, expected := range reference.Factories {
		t.Run(model, func(t *testing.T) { checkExperimentFactoryBoundary(t, model, expected) })
	}
}
func factoryBoundaryJSONEqual(t *testing.T, left, right []byte) bool {
	t.Helper()
	var a, b any
	decodeBoundaryJSON(t, left, &a)
	decodeBoundaryJSON(t, right, &b)
	return equal(a, b)
}

func checkExperimentFactoryBoundary(t *testing.T, model string, expected json.RawMessage) {
	t.Helper()
	first := experimentFactoryValues(model)
	actual, err := json.Marshal(first)
	if err != nil {
		t.Fatal(err)
	}
	if !factoryBoundaryJSONEqual(t, actual, expected) {
		t.Fatal("source constructor defaults differ", string(actual), string(expected))
	}
	for key := range first {
		delete(first, key)
	}
	second, err := json.Marshal(experimentFactoryValues(model))
	if err != nil {
		t.Fatal(err)
	}
	if !factoryBoundaryJSONEqual(t, second, expected) {
		t.Fatal("constructor defaults share mutable state")
	}
}

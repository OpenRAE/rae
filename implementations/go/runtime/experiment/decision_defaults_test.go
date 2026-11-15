package experiment

import (
	"encoding/json"
	"os"
	"testing"
)

func TestDecisionReconstructsIndependentNestedConstructorDefaults(t *testing.T) {
	raw, err := os.ReadFile("testdata/decision-defaults-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Cases []struct {
			Name     string          `json:"name"`
			Input    json.RawMessage `json:"input"`
			Document json.RawMessage `json:"document"`
			ID       string          `json:"id"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(raw, &reference); err != nil {
		t.Fatal(err)
	}
	for _, item := range reference.Cases {
		t.Run(item.Name, func(t *testing.T) {
			got, decodeErr := DecodeDecision(item.Input)
			if decodeErr != nil {
				t.Fatal(decodeErr)
			}
			if got.ID() != item.ID || !same(json.RawMessage(got.JSON()), item.Document) {
				t.Fatalf("nested constructor projection differs: %s", got.SchemaVersion())
			}
		})
	}
}

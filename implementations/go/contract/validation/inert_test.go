package validation

import (
	"encoding/json"
	"os"
	"testing"
)

func TestInertProfileReferenceVerdicts(t *testing.T) {
	if _, err := inertMeta(); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile("testdata/inert-verdicts.json")
	if err != nil {
		t.Fatal(err)
	}
	var recording struct {
		Cases []inertCase `json:"cases"`
	}
	if err := json.Unmarshal(data, &recording); err != nil {
		t.Fatal(err)
	}
	if len(recording.Cases) != 33 {
		t.Fatal("reference inventory changed")
	}
	for _, c := range recording.Cases {
		t.Run(c.Name, func(t *testing.T) { checkInertCase(t, c) })
	}
}

type inertCase struct {
	Name    string          `json:"name"`
	Schema  json.RawMessage `json:"schema"`
	Value   json.RawMessage `json:"value"`
	Valid   bool            `json:"valid"`
	Minimum int             `json:"minimum_evaluations"`
}

func checkInertCase(t *testing.T, c inertCase) {
	t.Helper()
	limits := InertLimits{MaxBytes: 1048576, MaxDepth: 16, MaxNodes: 4096, MaxScalarBytes: 1048576, MaxReferences: 128, MaxEvaluations: 65536}
	err := CheckInertSchema(c.Schema, c.Value, inertSafeKeywords(), limits)
	if (err == nil) != c.Valid {
		t.Fatalf("got %v; reference accepted=%v", err, c.Valid)
	}
	if !c.Valid {
		return
	}
	limits.MaxEvaluations = c.Minimum
	if err := CheckInertSchema(c.Schema, c.Value, inertSafeKeywords(), limits); err != nil {
		t.Fatalf("reference budget %d: %v", c.Minimum, err)
	}
	limits.MaxEvaluations--
	if err := CheckInertSchema(c.Schema, c.Value, inertSafeKeywords(), limits); err == nil {
		t.Fatal("accepted below reference budget")
	}
}

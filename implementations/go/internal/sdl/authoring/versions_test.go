package authoring

import (
	"encoding/json"
	"os"
	"testing"
)

func TestVersionReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/versions.json")
	if err != nil {
		t.Fatal(err)
	}
	var rows []versionVector
	if err = json.Unmarshal(raw, &rows); err != nil {
		t.Fatal(err)
	}
	for _, row := range rows {
		t.Run(row.Requested, func(t *testing.T) { checkVersionVector(t, row) })
	}
}

type versionVector struct {
	Requested string           `json:"requested"`
	Valid     bool             `json:"valid"`
	Actuals   map[string]*bool `json:"actuals"`
}

func checkVersionVector(t *testing.T, row versionVector) {
	t.Helper()
	spec, err := versionSpec(row.Requested)
	if (err == nil) != row.Valid {
		t.Fatalf("valid=%v, want %v", err == nil, row.Valid)
	}
	if err != nil {
		return
	}
	for actual, want := range row.Actuals {
		if want == nil {
			continue
		}
		if got := spec.accepts(actual); got != *want {
			t.Errorf("accepts(%q)=%v, want %v", actual, got, *want)
		}
	}
}

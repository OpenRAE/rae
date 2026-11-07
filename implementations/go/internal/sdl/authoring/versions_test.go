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
	var rows []struct {
		Requested string
		Valid     bool
		Actuals   map[string]*bool
	}
	if err = json.Unmarshal(raw, &rows); err != nil {
		t.Fatal(err)
	}
	for _, row := range rows {
		t.Run(row.Requested, func(t *testing.T) {
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
		})
	}
}

package governance

import (
	"slices"
	"testing"
)

func TestPublicationCompatibilityReference(t *testing.T) {
	for _, tc := range readReference[[]struct {
		Name, Old, New string
		Property       bool
		Changes        []string
	}](t, "publication-compatibility-reference") {
		t.Run(tc.Name, func(t *testing.T) {
			oldValue, err := decodeJSON([]byte(tc.Old), 0, false)
			if err != nil {
				t.Fatal(err)
			}
			newValue, err := decodeJSON([]byte(tc.New), 0, false)
			if err != nil {
				t.Fatal(err)
			}
			var changes []string
			if tc.Property {
				changes, err = publicationPropertyChanges("properties/value", oldValue, newValue)
			} else {
				changes, err = publicationBreakingChanges(oldValue, newValue)
			}
			if err != nil || !slices.Equal(changes, tc.Changes) {
				t.Fatalf("compatibility changes=%q error=%v want=%q", changes, err, tc.Changes)
			}
		})
	}
}

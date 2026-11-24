package realization

import (
	"encoding/json"
	"testing"
)

func TestLegacyStructureKeepsExactOpenAndRecordSemantics(t *testing.T) {
	exact := map[string]any{"kind": "exact"}
	open := map[string]any{"kind": "open"}
	fields := map[string]any{"name": exact}
	closed := map[string]any{"kind": "record", "fields": fields}
	additional := map[string]any{"kind": "record", "fields": fields, "additional": true}
	before := map[string]any{"name": "a", "other": "same"}
	for _, test := range []struct {
		name                   string
		rule, expected, actual any
		want                   bool
	}{
		{"exact equal", exact, "a", "a", true},
		{"exact changed", exact, "a", "b", false},
		{"open changed", open, "a", "b", true},
		{"open taxonomy", map[string]any{"kind": "open", "taxonomy_sentinel": true}, "a", "linux", true},
		{"taxonomy null", map[string]any{"kind": "open", "taxonomy_sentinel": true}, "a", nil, false},
		{"taxonomy unknown", map[string]any{"kind": "open", "taxonomy_sentinel": true}, "a", termUnknown, false},
		{"taxonomy other", map[string]any{"kind": "open", "taxonomy_sentinel": true}, "a", "other", false},
		{"unknown rule", map[string]any{"kind": "future"}, "a", "a", false},
		{"record unchanged", closed, before, before, true},
		{"record type", closed, before, []any{}, false},
		{"expected type", closed, []any{}, before, false},
		{"missing field", closed, before, map[string]any{}, false},
		{"missing expected field", closed, map[string]any{}, before, false},
		{"changed field", closed, before, map[string]any{"name": "b"}, false},
		{"changed extra", closed, before, map[string]any{"name": "a", "other": "changed"}, false},
		{"new extra", closed, before, map[string]any{"name": "a", "new": true}, false},
		{"additional field", additional, before, map[string]any{"name": "a", "new": true}, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			if got := legacyStructureMatches(test.rule, test.expected, test.actual, 0); got != test.want {
				t.Fatalf("structure match=%t, want %t", got, test.want)
			}
		})
	}
	if legacyStructureMatches(open, nil, nil, 65) {
		t.Fatal("over-depth structure was accepted")
	}
}

func TestLegacyCollectionsUseUniqueScalarIdentityAndRequiredMembers(t *testing.T) {
	identity, err := projectionDigest([]any{"a"})
	if err != nil {
		t.Fatal(err)
	}
	member := map[string]any{"kind": "record", "fields": map[string]any{"id": map[string]any{"kind": "exact"}}}
	rule := map[string]any{"kind": "collection", "identity_fields": []any{"id"}, "members": map[string]any{identity: member}}
	first := []any{map[string]any{"id": "a"}}
	for _, test := range []struct {
		name             string
		expected, actual any
		want             bool
	}{
		{"same", first, first, true},
		{"invalid expected", "a", first, false},
		{"invalid actual", first, "a", false},
		{"missing", first, []any{}, false},
		{"changed identity", first, []any{map[string]any{"id": "b"}}, false},
		{"duplicate", first, []any{map[string]any{"id": "a"}, map[string]any{"id": "a"}}, false},
		{"nonrecord", first, []any{"a"}, false},
		{"nonscalar identity", first, []any{map[string]any{"id": map[string]any{}}}, false},
		{"missing identity", first, []any{map[string]any{}}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			if got := legacyStructureMatches(rule, test.expected, test.actual, 0); got != test.want {
				t.Fatalf("collection match=%t, want %t", got, test.want)
			}
		})
	}
	rule["additional"] = true
	if !legacyStructureMatches(rule, first, []any{map[string]any{"id": "a"}, map[string]any{"id": "b"}}, 0) {
		t.Fatal("allowed additional member refused")
	}
	if legacyStructureMatches(rule, []any{}, []any{}, 0) {
		t.Fatal("rule member absent from expected collection accepted")
	}
	for _, scalar := range []any{true, json.Number("1"), "a"} {
		if index, ok := legacyIndexedCollection([]any{map[string]any{"id": scalar}}, []any{"id"}); !ok || len(index) != 1 {
			t.Fatalf("scalar identity %v refused", scalar)
		}
	}
}

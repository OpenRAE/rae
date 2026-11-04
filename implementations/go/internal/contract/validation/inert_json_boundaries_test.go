package validation

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestInertJSONReaderRefusesExhaustedOrMalformedValues(t *testing.T) {
	limits := InertLimits{MaxBytes: 4096, MaxDepth: 8, MaxNodes: 32, MaxScalarBytes: 64}
	for _, raw := range []string{"", "{", "[1,", "true false", "1e10000", "1e-10000", "[1,2,3,4,5,6]", `{"long-key":"long-value"}`, strings.Repeat("[", 10) + "0" + strings.Repeat("]", 10)} {
		t.Run(raw, func(t *testing.T) {
			bounded := limits
			if raw == "[1,2,3,4,5,6]" {
				bounded.MaxNodes = 3
			}
			if strings.Contains(raw, "long-key") {
				bounded.MaxScalarBytes = 4
			}
			if _, err := readInert([]byte(raw), bounded); err == nil {
				t.Fatal("accepted malformed or exhausted inert JSON")
			}
		})
	}
}

func TestInertPointerResolvesEscapedMembersAndArrayIndexes(t *testing.T) {
	root, err := readInert([]byte(`{"a/b":{"~key":[{"value":7},true]}}`), InertLimits{MaxBytes: 4096, MaxDepth: 8, MaxNodes: 32, MaxScalarBytes: 64})
	if err != nil {
		t.Fatal(err)
	}
	selected := inertPointer(root, "#/a~1b/~0key/0/value")
	if selected == nil || selected.value != json.Number("7") {
		t.Fatal("escaped array member did not resolve")
	}
	for _, ref := range []string{"#", "foreign", "#/%zz", "#/a~1b/~0key/-1", "#/a~1b/~0key/2", "#/a~1b/~0key/unknown", "#/missing/child", "#/a~1b/~0key/0/value/child"} {
		if inertPointer(root, ref) != nil {
			t.Fatal("resolved absent inert pointer", ref)
		}
	}
	// Work accounting must include every nested candidate and instance member.
	value := map[string]any{"a": []any{true, json.Number("7")}}
	if inertComparisonSize(value) != 5 || inertKeywordCost("const", value, value) != 10 || inertKeywordCost("enum", []any{value, value}, value) != 20 {
		t.Fatal("nested comparison work was not charged")
	}
}

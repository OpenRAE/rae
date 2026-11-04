package admission

import (
	"encoding/json"
	"fmt"
	"testing"
)

// This checks the reference comparison component. Parameter and binding
// admission retain their own closed schemas and declared scalar-type checks.
func TestReferenceValueComparisonMatchesIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Left, Right json.RawMessage
			Equal       bool
		}
	}
	readFullReferenceJSON(t, "testdata/reference-json-equality.json", &reference)
	if len(reference.Cases) != 529 {
		t.Fatal("independent reference comparison inventory changed")
	}
	for index, c := range reference.Cases {
		t.Run(fmt.Sprintf("%03d", index), func(t *testing.T) {
			left, right := decodeRuleObject(t, string(c.Left)), decodeRuleObject(t, string(c.Right))
			if actual := referenceJSONEqual(left, right); actual != c.Equal {
				t.Fatalf("reference comparison=%v, Python=%v", actual, c.Equal)
			}
		})
	}
}

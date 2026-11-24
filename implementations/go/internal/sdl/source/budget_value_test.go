package source

import (
	"encoding/json"
	"testing"
)

func TestNormalizedCompositionAccounting(t *testing.T) {
	// Python CompositionBudget counts the root, keys, values and list members:
	// 8 nodes and 6 UTF-8 string bytes. JSON punctuation and escapes are not bytes.
	value := map[string]any{"name": "a", "x": []any{true, nil, json.Number("3")}}
	for _, c := range []struct {
		name  string
		nodes int
		bytes int64
		valid bool
	}{
		{"at-boundary", 8, 6, true}, {"below-nodes", 7, 6, false}, {"below-bytes", 8, 5, false},
	} {
		t.Run(c.name, func(t *testing.T) {
			limits := DefaultLimits()
			limits.MaxComposedNodes = c.nodes
			limits.MaxComposedBytes = c.bytes
			budget, err := NewBudget(limits)
			if err != nil {
				t.Fatal(err)
			}
			if err = budget.AddValue(value); (err == nil) != c.valid {
				t.Fatalf("valid=%v, want %v: %v", err == nil, c.valid, err)
			}
		})
	}
}
func TestNormalizedCompositionCountsRepeatedValues(t *testing.T) {
	shared := map[string]any{"k": "a"}
	limits := DefaultLimits()
	limits.MaxComposedNodes = 6
	budget, err := NewBudget(limits)
	if err != nil {
		t.Fatal(err)
	}
	if budget.AddValue([]any{shared, shared}) == nil {
		t.Fatal("shared value escaped repeated node accounting")
	}
}
func TestNormalizedCompositionRefusesNativeCarrier(t *testing.T) {
	budget, err := NewBudget(DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	if budget.AddValue(struct{ Secret string }{"private"}) == nil {
		t.Fatal("accepted a native carrier")
	}
}

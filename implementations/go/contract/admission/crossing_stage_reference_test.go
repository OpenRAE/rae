package admission

import (
	"encoding/json"
	"testing"
)

func TestCrossingStageTransitionsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Chains map[string][]json.RawMessage `json:"chains"`
		Cases  []struct {
			Chain    string          `json:"chain"`
			Name     string          `json:"name"`
			Record   json.RawMessage `json:"record"`
			Admitted bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/crossing-stage-verdicts.json", &reference)
	if len(reference.Cases) != 58 || len(reference.Chains) != 3 {
		t.Fatal("independent crossing-stage inventory changed")
	}
	indexes := map[string]*crossingIndex{}
	for name, records := range reference.Chains {
		indexes[name] = referenceCrossingIndex(t, records)
	}
	for _, c := range reference.Cases {
		t.Run(c.Chain+"/"+c.Name, func(t *testing.T) {
			index := indexes[c.Chain]
			if index == nil {
				t.Fatal("missing independent crossing history")
			}
			err := index.stage(decodeRuleObject(t, string(c.Record)))
			if (err == nil) != c.Admitted {
				t.Fatalf("crossing stage differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

func referenceCrossingIndex(t *testing.T, records []json.RawMessage) *crossingIndex {
	t.Helper()
	index := &crossingIndex{records: map[string]any{}, stages: map[string]any{}}
	for _, raw := range records {
		if err := index.register(decodeRuleObject(t, string(raw))); err != nil {
			t.Fatal("independent crossing history:", err)
		}
	}
	return index
}

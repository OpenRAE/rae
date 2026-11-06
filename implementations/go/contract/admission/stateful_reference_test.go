package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestStatefulReferenceJoinsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Baselines map[string]json.RawMessage `json:"baselines"`
		Cases     []struct {
			Baseline string            `json:"baseline"`
			Name     string            `json:"name"`
			Changes  []referenceChange `json:"changes"`
			Admitted bool              `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/stateful-verdicts.json", &reference)
	if len(reference.Cases) != 37 || len(reference.Baselines) != 4 {
		t.Fatal("independent stateful join inventory changed")
	}
	for _, c := range reference.Cases {
		t.Run(c.Baseline+"/"+c.Name, func(t *testing.T) {
			value := decodeRuleObject(t, string(reference.Baselines[c.Baseline]))
			for _, change := range c.Changes {
				applyReferenceChange(t, value, change)
			}
			err := statefulReferences(validation.Invocation{Instance: value})
			if (err == nil) != c.Admitted {
				t.Fatalf("stateful reference joins differ from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestTemporalSourceOwnershipMatchesIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Baselines map[string]json.RawMessage
		Cases     []struct {
			Baseline, Name string
			Changes        []referenceChange
			Admitted       bool
		}
	}
	readFullReferenceJSON(t, "testdata/temporal-source-verdicts.json", &reference)
	if len(reference.Cases) != 35 {
		t.Fatal("temporal source inventory changed", len(reference.Cases))
	}
	for _, c := range reference.Cases {
		t.Run(c.Baseline+"/"+c.Name, func(t *testing.T) {
			raw, ok := reference.Baselines[c.Baseline]
			if !ok {
				t.Fatal("missing source baseline")
			}
			v := decodeRuleObject(t, string(raw))
			for _, change := range c.Changes {
				applyReferenceChange(t, v, change)
			}
			err := temporalSource(validation.Invocation{Instance: v})
			if (err == nil) != c.Admitted {
				t.Fatalf("temporal source differs from native owner (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

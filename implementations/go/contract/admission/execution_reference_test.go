package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestExecutionAccountingAndDifficultyMatchPython(t *testing.T) {
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
	readFullReferenceJSON(t, "testdata/execution-model-verdicts.json", &reference)
	if len(reference.Cases) != 47 || len(reference.Baselines) != 3 {
		t.Fatal("independent execution model inventory changed")
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Baseline+"/"+c.Name, func(t *testing.T) {
			value := decodeRuleObject(t, string(reference.Baselines[c.Baseline]))
			for _, change := range c.Changes {
				applyReferenceChange(t, value, change)
			}
			raw := controlJSON(t, value)
			limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
			err := e.low.CheckLocal(termExperimentRunV1, raw, limits)
			if err == nil {
				err = e.checkModels(termExperimentRunV1, raw, limits)
			}
			if (err == nil) != c.Admitted {
				t.Fatalf("execution model differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

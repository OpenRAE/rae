package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestServiceMaterializationJoinsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Baseline json.RawMessage `json:"baseline"`
		Cases    []struct {
			Name     string            `json:"name"`
			Changes  []referenceChange `json:"changes"`
			Admitted bool              `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/service-verdicts.json", &reference)
	if len(reference.Cases) != 25 {
		t.Fatal("independent service materialization inventory changed")
	}
	for index, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			value := decodeRuleObject(t, string(reference.Baseline))
			for _, change := range c.Changes {
				applyReferenceChange(t, value, change)
			}
			err := serviceMaterialization(validation.Invocation{Instance: value})
			if (err == nil) != c.Admitted {
				t.Fatalf("service reference case %d differs from Python (admitted=%v): %v", index, c.Admitted, err)
			}
		})
	}
}

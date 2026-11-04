package admission

import (
	"encoding/json"
	"fmt"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestComparisonDependencyAndImpactPathsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	count := 0
	for shard := 1; shard <= 3; shard++ {
		var reference struct {
			Cases []struct {
				Name     string          `json:"name"`
				Value    json.RawMessage `json:"value"`
				Admitted bool            `json:"admitted"`
			} `json:"cases"`
		}
		readFullReferenceJSON(t, fmt.Sprintf("testdata/comparison-verdicts-%02d.json", shard), &reference)
		for _, c := range reference.Cases {
			count++
			t.Run(c.Name, func(t *testing.T) {
				err := e.comparisonResult(validation.Invocation{Instance: decodeRuleObject(t, string(c.Value))})
				if (err == nil) != c.Admitted {
					t.Fatalf("comparison semantics differ from Python (admitted=%v): %v", c.Admitted, err)
				}
			})
		}
	}
	if count != 320 {
		t.Fatal("independent comparison inventory changed")
	}
}

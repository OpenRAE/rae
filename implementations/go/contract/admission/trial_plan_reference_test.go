package admission

import (
	"encoding/json"
	"fmt"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestResealedTrialPlanJoinsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	count := 0
	for n := 1; n <= 3; n++ {
		var reference struct {
			Cases []struct {
				Name     string
				Value    json.RawMessage
				Admitted bool
			}
		}
		readFullReferenceJSON(t, fmt.Sprintf("testdata/trial-plan-join-verdicts-%02d.json", n), &reference)
		for _, c := range reference.Cases {
			t.Run(c.Name, func(t *testing.T) {
				_, err := e.Validate("admitted-trial-plan-v1", c.Value, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, nil)
				if (err == nil) != c.Admitted {
					t.Fatalf("resealed plan differs from native validation (admitted=%v): %v", c.Admitted, err)
				}
			})
			count++
		}
	}
	if count != 54 {
		t.Fatal("resealed trial plan inventory changed", count)
	}
}

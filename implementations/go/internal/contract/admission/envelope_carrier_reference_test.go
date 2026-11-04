package admission

import (
	"encoding/json"
	"fmt"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestEnvelopeCarrierConcernAndConfigurationJoinsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	count := 0
	for shard := 1; shard <= 4; shard++ {
		var reference struct {
			Cases []struct {
				Name     string
				Value    json.RawMessage
				Admitted bool
			}
		}
		readFullReferenceJSON(t, fmt.Sprintf("testdata/envelope-carrier-verdicts-%02d.json", shard), &reference)
		for _, c := range reference.Cases {
			count++
			t.Run(c.Name, func(t *testing.T) {
				_, err := e.Validate("realization-envelope-v1", c.Value, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, nil)
				if (err == nil) != c.Admitted {
					t.Fatalf("envelope carrier differs from Python (admitted=%v): %v", c.Admitted, err)
				}
			})
		}
	}
	if count != 447 {
		t.Fatal("independent envelope carrier inventory changed", count)
	}
}

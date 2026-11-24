package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestCleanupRetryAndResetCoverageMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Name     string
			Value    json.RawMessage
			Admitted bool
		}
	}
	readFullReferenceJSON(t, "testdata/cleanup-plan-verdicts.json", &reference)
	if len(reference.Cases) != 31 {
		t.Fatal("cleanup plan inventory changed", len(reference.Cases))
	}
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			err := cleanupPlan(validation.Invocation{Instance: decodeRuleObject(t, string(c.Value))})
			if (err == nil) != c.Admitted {
				t.Fatalf("cleanup plan differs from native admission (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

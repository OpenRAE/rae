package admission

import (
	"encoding/json"
	"testing"
)

func TestEnvelopeDomainBindingsAndWitnessesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Name     string
			Value    json.RawMessage
			Admitted bool
		}
	}
	readFullReferenceJSON(t, "testdata/envelope-expression-verdicts.json", &reference)
	if len(reference.Cases) != 159 {
		t.Fatal("independent expression inventory changed", len(reference.Cases))
	}
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			err := envelopeExpression(decodeRuleObject(t, string(c.Value)))
			if (err == nil) != c.Admitted {
				t.Fatalf("envelope expression differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

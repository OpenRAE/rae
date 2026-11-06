package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestPortablePolicyAndStatefulPredicatesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Kind, Name string
			Value      json.RawMessage
			Admitted   bool
		}
	}
	readFullReferenceJSON(t, "testdata/policy-state-verdicts.json", &reference)
	if len(reference.Cases) != 241 {
		t.Fatal("independent policy/resource inventory changed", len(reference.Cases))
	}
	for _, c := range reference.Cases {
		t.Run(c.Kind+"/"+c.Name, func(t *testing.T) {
			v := decodeRuleObject(t, string(c.Value))
			var err error
			switch c.Kind {
			case "policy":
				err = executionPolicy(v)
			case "document":
				err = policyDocument(validation.Invocation{Instance: v})
			case "effective":
				err = effectivePolicy(v)
			case "artifact":
				err = generatedArtifact(v)
			case "volume":
				err = persistentVolume(v)
			default:
				t.Fatal("unknown reference predicate")
			}
			if (err == nil) != c.Admitted {
				t.Fatalf("native local predicate admitted=%v: %v", c.Admitted, err)
			}
		})
	}
}

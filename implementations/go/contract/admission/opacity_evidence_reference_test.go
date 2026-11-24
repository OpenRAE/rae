package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestOpacityEvidenceCommitmentsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Kind, Name string
			Value      json.RawMessage
			Admitted   bool
		}
	}
	readFullReferenceJSON(t, "testdata/opacity-evidence-verdicts.json", &reference)
	if len(reference.Cases) != 87 {
		t.Fatal("opacity evidence inventory changed", len(reference.Cases))
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Kind+"/"+c.Name, func(t *testing.T) {
			v := decodeRuleObject(t, string(c.Value))
			i := validation.Invocation{Instance: v}
			var err error
			switch c.Kind {
			case "bounded":
				err = e.opacityEvidence(i)
			case "model":
				err = e.opacityModelEvidence(i)
			default:
				t.Fatal("unknown opacity surface")
			}
			if (err == nil) != c.Admitted {
				t.Fatalf("opacity evidence differs from native admission (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

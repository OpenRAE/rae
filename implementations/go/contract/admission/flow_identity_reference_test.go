package admission

import (
	"encoding/json"
	"slices"
	"strconv"
	"testing"
)

func TestFlowBindingIdentitiesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Kind, Identity string
			Value          json.RawMessage
			Related        []string
		}
	}
	readFullReferenceJSON(t, "testdata/flow-identity-verdicts.json", &reference)
	if len(reference.Cases) != 36 {
		t.Fatal("flow identity reference inventory changed", len(reference.Cases))
	}
	for n, c := range reference.Cases {
		t.Run(c.Kind+strconv.Itoa(n), func(t *testing.T) {
			v := decodeRuleObject(t, string(c.Value))
			var identity string
			var related []string
			switch c.Kind {
			case "control":
				identity, related = flowControlIdentity(v)
			case "crossing":
				identity, related = flowCrossingIdentity(v)
			default:
				t.Fatal("unknown identity projection")
			}
			if identity != c.Identity || !slices.Equal(related, c.Related) {
				t.Fatalf("incumbent identity differs: %s %v; expected %s %v", identity, related, c.Identity, c.Related)
			}
		})
	}
}

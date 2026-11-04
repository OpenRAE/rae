package admission

import (
	"fmt"
	"testing"
)

func TestMixedTrialProjectionAndEffectGrantsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	var reference struct{ Cases []mixedTrialReferenceCase }
	readFullReferenceJSON(t, "testdata/mixed-trial-verdicts.json", &reference)
	if len(reference.Cases) != 48 {
		t.Fatal("independent mixed trial inventory changed")
	}
	for index, c := range reference.Cases {
		t.Run(fmt.Sprintf("%02d/%s", index, c.Profile), func(t *testing.T) {
			v, context := mixedTrialContext(t, e, c)
			r := mixedResolution{snapshot: context.snapshot}
			err := r.trial(v)
			if (err == nil) != c.Admitted {
				t.Fatalf("mixed trial differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

type mixedTrialReferenceCase struct {
	Profile                                          string
	Projection, Effects, Resource, Overlap, Admitted bool
}

func mixedTrialContext(t *testing.T, e *Validator, c mixedTrialReferenceCase) (any, *mixedTestContext) {
	t.Helper()
	raw, context := mixedContextFixture(t, e, c.Profile)
	v := decodeRuleObject(t, string(raw))
	id := stringAt(v, "profile_id")
	context.snapshot.ProjectionMembership = map[[2]string]bool{}
	for component := range object(at(v, "components")) {
		context.snapshot.ProjectionMembership[[2]string{id, component}] = c.Projection
	}
	context.snapshot.AllocationEffects = map[[2]string][]string{}
	for allocation := range object(at(v, "allocations")) {
		var effects []string
		if c.Effects {
			effect := "effect:" + allocation
			if c.Overlap {
				effect = "effect:shared"
			}
			effects = []string{effect}
		}
		context.snapshot.AllocationEffects[[2]string{id, allocation}] = effects
	}
	context.snapshot.ResourceRefs = map[string][]string{}
	if c.Resource {
		context.snapshot.ResourceRefs[id] = nil
	}
	return v, context
}

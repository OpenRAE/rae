package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestAdmittedPlanIntegrityAndAuthorityJoins(t *testing.T) {
	e := boundTestOwner(t)
	for _, name := range []string{"minimal", "factorial-randomized", "typed-treatment", "parallel-isolated"} {
		t.Run(name, func(t *testing.T) {
			v := fixtureObject(t, "fixtures/plans/admitted-trial-plan-v1/valid/"+name+".json")
			if err := validateTestDocument(t, e, "admitted-trial-plan-v1", v, nil); err != nil {
				t.Fatal(err)
			}
			object(v["admission"])["entry_count"] = json.Number("999")
			resealPlan(t, e, v)
			if err := e.trialPlan(validation.Invocation{Key: validation.Key{ContractID: "admitted-trial-plan-v1"}, Instance: v, Root: v}); err == nil {
				t.Error("accepted resealed contradictory entry count")
			}
		})
	}
}

func resealPlan(t *testing.T, e *Validator, v any) {
	t.Helper()
	root, err := e.defaulted("admitted-trial-plan-v1", v)
	if err != nil {
		t.Fatal(err)
	}
	trialProjection(root)
	delete(object(root), "plan_digest")
	digest, err := jsonDigest(root)
	if err != nil {
		t.Fatal(err)
	}
	object(v)["plan_digest"] = digest
}

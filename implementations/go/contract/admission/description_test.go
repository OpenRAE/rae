package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestTypedDescriptionsRemainDescriptive(t *testing.T) {
	e := boundTestOwner(t)
	v := fixtureObject(t, "fixtures/experiment-core/experiment-evidence-record-v1/valid/partial-description.json")
	rule, ok := e.checker("evidence-description-nonauthoritative")
	if !ok {
		t.Fatal("missing description rule")
	}
	if err := rule.check(validation.Invocation{Instance: v}); err != nil {
		t.Fatal(err)
	}
	fact := object(array(at(v, "typed_description", "facts"))[0])
	object(fact["value"])["origin"] = "author"
	if err := rule.check(validation.Invocation{Instance: v}); err == nil {
		t.Error("accepted author authority in description")
	}
	object(fact["value"])["origin"] = "backend"
	v["redaction_state"] = "withheld"
	if err := rule.check(validation.Invocation{Instance: v}); err == nil {
		t.Error("withheld evidence carried known values")
	}
}

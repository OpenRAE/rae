package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestConditionSignatureDefaultsToFixed(t *testing.T) {
	absent, err := conditionSignature(map[string]any{})
	if err != nil {
		t.Fatal(err)
	}
	explicit, err := conditionSignature(map[string]any{"difficulty_condition": "fixed"})
	if err != nil {
		t.Fatal(err)
	}
	if absent != explicit {
		t.Error("omitted and explicit fixed difficulty have different meanings")
	}
}

func TestTypedSelectionsEstablishBindingCoverage(t *testing.T) {
	v := decodeRuleObject(t, `{"factorial_design":{"profile":"factorial-treatments-v1"},"binding_semantics":"explicit-required","binding_descriptors":{"descriptors":[]},"run_plan":{"allocation":{"compared_conditions":["condition"],"condition_assignments":{"condition":{"required_selections":[{}]}}}}}`)
	if err := bindingSources(validation.Invocation{Instance: v}); err != nil {
		t.Fatal(err)
	}
	assignment := object(at(v, "run_plan", "allocation", "condition_assignments", "condition"))
	assignment["required_selections"] = []any{}
	if err := bindingSources(validation.Invocation{Instance: v}); err == nil {
		t.Error("accepted condition without a binding or selection")
	}
}

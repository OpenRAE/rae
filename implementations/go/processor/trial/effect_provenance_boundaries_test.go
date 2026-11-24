package trial

import (
	"encoding/json"
	"maps"
	"testing"
)

func TestTreatmentEffectsIgnoreDescriptiveProvenanceButRetainOperativeConstraints(t *testing.T) {
	left := json.RawMessage(`{"capability_constraints":[{"field_pointer":"/z","allowed_values":[2,1]},{"field_pointer":"/a","allowed_values":[false,true]}],"realization_constraints":[{"field_pointer":"/x","provenance":{"note":"first"},"constraint":{"kind":"exact","value":1}}]}`)
	right := json.RawMessage(`{"capability_constraints":[{"field_pointer":"/a","allowed_values":[true,false]},{"field_pointer":"/z","allowed_values":[1,2]}],"realization_constraints":[{"field_pointer":"/x","provenance":{"note":"different"},"constraint":{"kind":"exact","value":1}}]}`)
	a, err := operativeProvenance(left)
	if err != nil {
		t.Fatal(err)
	}
	b, err := operativeProvenance(right)
	if err != nil {
		t.Fatal(err)
	}
	if !sameJSON(a, b) {
		t.Fatal("descriptive provenance or unordered capability values changed effective treatment")
	}
	var changed map[string]json.RawMessage
	if decode(right, &changed) != nil {
		t.Fatal("provenance fixture")
	}
	for _, field := range []string{"realization_designations", "explicitness", "parameter_derivations"} {
		input := maps.Clone(changed)
		input[field] = json.RawMessage(`[{}]`)
		raw, encodeErr := encoded(input)
		if encodeErr != nil {
			t.Fatal(encodeErr)
		}
		effect, checkErr := operativeProvenance(raw)
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		if sameJSON(a, effect) {
			t.Fatal("operative provenance was erased", field)
		}
	}
}
func TestFactorialSelectionRefusesMissingCoverageAndUnresolvedTypedOutcomes(t *testing.T) {
	for _, test := range []struct {
		name, design, bindings string
		policy                 bool
	}{
		{"malformed-design", `{`, `null`, false}, {"malformed-bindings", `{"profile":"factorial-bindings-v1"}`, `{`, false}, {"competing-policies", `{"profile":"factorial-bindings-v1"}`, `null`, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			spec := experimentSpec{Factorial: json.RawMessage(test.design), Bindings: json.RawMessage(test.bindings)}
			if test.policy {
				spec.RunPlan.Policies = map[string]selectionPolicy{"policy": {}}
			}
			if _, err := factorialRows(Request{}, spec, []coordinate{{}}, nil); err == nil {
				t.Fatal("ambiguous factorial design admitted")
			}
		})
	}
	reference := descriptor{Target: descriptorTarget{Plane: "scenario", Point: "point"}, Value: selectionOutcome{Kind: "reference", ReferenceID: "ref"}}
	if _, err := factorialScalarSelections(coordinate{}, []descriptor{reference}, "factorial-bindings-v1"); err == nil {
		t.Fatal("nonliteral scalar factorial outcome admitted")
	}
	if _, err := factorialRow(Request{}, experimentSpec{}, coordinate{}, nil, "factorial-bindings-v1", map[string]json.RawMessage{"point": nil}); err == nil {
		t.Fatal("uncovered factorial point admitted")
	}
	reference.Value = selectionOutcome{Kind: "literal", Value: json.RawMessage(`1`)}
	if _, err := factorialRow(Request{}, experimentSpec{}, coordinate{}, []descriptor{reference}, "factorial-bindings-v1", map[string]json.RawMessage{"foreign": nil}); err == nil {
		t.Fatal("foreign factorial point admitted")
	}
	if _, err := factorialTypedSelections(Request{}, experimentSpec{}, coordinate{}); err == nil {
		t.Fatal("typed selection without allocation admitted")
	}
	if _, err := factorialTreatment(Request{}, json.RawMessage(`{}`)); err == nil {
		t.Fatal("unowned typed selection admitted")
	}
	if err := factorialBindingSelection(Request{}, reference, selectionRow{}); err == nil {
		t.Fatal("binding without selected outcome admitted")
	}
	if _, err := factorialSignature(trialEntry{Bindings: []json.RawMessage{json.RawMessage(`{`)}}, nil, false); err == nil {
		t.Fatal("malformed operative binding admitted")
	}
	if _, err := factorialSignature(trialEntry{Configurations: []json.RawMessage{json.RawMessage(`{`)}}, nil, false); err == nil {
		t.Fatal("malformed participant effect admitted")
	}
}

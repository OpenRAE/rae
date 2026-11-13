package admission

import "testing"

func TestConstraintDomainsKeepBooleanAndNumericBoundaryMeaning(t *testing.T) {
	owner := boundTestOwner(t)
	for _, test := range []struct{ name, domain, actual, status string }{
		{"null rejects scalar", `{"kind":"null"}`, `1`, "nonconformant"},
		{"enum member", `{"kind":"enum","values":[1,3]}`, `3`, "conformant"},
		{"enum outside", `{"kind":"enum","values":[1,3]}`, `2`, "nonconformant"},
		{"boolean accepts false", `{"kind":"boolean"}`, `false`, "conformant"},
		{"boolean rejects integer", `{"kind":"boolean"}`, `0`, "nonconformant"},
		{"exact boolean", `{"kind":"boolean","value":true}`, `false`, "nonconformant"},
		{"integer inside", `{"kind":"numeric-interval","numeric_type":"integer","lower":1,"upper":3,"lower_closed":false,"upper_closed":true}`, `2`, "conformant"},
		{"integer lower excluded", `{"kind":"numeric-interval","numeric_type":"integer","lower":1,"upper":3,"lower_closed":false,"upper_closed":true}`, `1`, "nonconformant"},
		{"integer upper included", `{"kind":"numeric-interval","numeric_type":"integer","lower":1,"upper":3}`, `3`, "conformant"},
		{"integer fractional", `{"kind":"numeric-interval","numeric_type":"integer","lower":1,"upper":3}`, `2.5`, "nonconformant"},
		{"number fractional", `{"kind":"numeric-interval","numeric_type":"number","lower":1,"upper":3}`, `2.5`, "conformant"},
	} {
		t.Run(test.name, func(t *testing.T) {
			constraint := constraintTestDocument(t, owner, `{"kind":"domain","domain":`+test.domain+`}`)
			result, err := EvaluateRealizationConstraint(constraint, constraintTestValue(t, owner, test.actual), DefaultConstraintLimits())
			if err != nil {
				t.Fatal(err)
			}
			if status := requireType[map[string]any](t, result.Document())["status"]; status != test.status {
				t.Fatalf("domain membership=%v, want %s", status, test.status)
			}
		})
	}
}

func TestConstraintDefinitionReferencesResolveAndKeepTheirHopLimit(t *testing.T) {
	owner := boundTestOwner(t)
	document := `{"semantic_profile":"test/v1","default_closure":{"posture":"closed","universe":"test","profile":"test/v1"},"definitions":{"first":{"kind":"definition-reference","target":"last"},"last":{"kind":"literal","value":7}},"root":{"kind":"definition-reference","target":"first"}}`
	constraint := constraintTestFragment(t, owner, RealizationConstraint, document)
	actual := constraintTestValue(t, owner, `7`)
	result, err := EvaluateRealizationConstraint(constraint, actual, DefaultConstraintLimits())
	if err != nil || requireType[map[string]any](t, result.Document())["status"] != "conformant" {
		t.Fatalf("definition chain did not resolve: %v %v", result, err)
	}
	limits := DefaultConstraintLimits()
	limits.MaxReferenceHops = 1
	result, err = EvaluateRealizationConstraint(constraint, actual, limits)
	if err != nil || requireType[map[string]any](t, result.Document())["status"] != "limit-exceeded" {
		t.Fatalf("definition hop ceiling ignored: %v %v", result, err)
	}
	limits.MaxDocumentScalarBytes = new(0)
	if limits.Validate() == nil {
		t.Fatal("zero document scalar ceiling accepted")
	}
}

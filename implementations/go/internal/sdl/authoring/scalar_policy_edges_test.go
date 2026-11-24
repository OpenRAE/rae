package authoring

import (
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestScalarPolicyConversionsPreserveStrictAndCoercingKinds(t *testing.T) {
	for _, test := range []struct {
		name   string
		value  any
		shapes []string
		want   any
		refuse bool
	}{
		{"true as number", true, []string{numberType}, json.Number("1.0"), false},
		{"false as number", false, []string{numberType}, json.Number("0.0"), false},
		{"integer text", "7", []string{integerType}, json.Number("7"), false},
		{"boolean text", "yes", []string{booleanType}, true, false},
		{"strict integer text", "7", []string{"integer!"}, nil, true},
		{"strict number text", "7", []string{strictNumberShape}, nil, true},
		{"strict numeric token", json.Number("2.5"), []string{strictNumberShape}, json.Number("2.5"), false},
		{"fractional number", float64(2.5), []string{numberType}, json.Number("2.5"), false},
		{"unknown shape", "value", []string{"custom"}, "value", false},
	} {
		t.Run(test.name, func(t *testing.T) {
			got, err := coerceScalar(test.value, test.shapes)
			if (err != nil) != test.refuse {
				t.Fatalf("scalar refusal=%v", err)
			}
			if !test.refuse {
				if diff := cmp.Diff(test.want, got); diff != "" {
					t.Fatal(diff)
				}
			}
		})
	}
}

func TestScalarBoundsVisitNestedMembersAndRefuseInvalidDefinitions(t *testing.T) {
	policy := scalarPolicy{Minimum: new("0"), Maximum: new("2")}
	if err := scalarBounds([]any{json.Number("1"), map[string]any{"value": json.Number("2")}}, policy); err != nil {
		t.Fatal(err)
	}
	for _, value := range []any{json.Number("NaN"), json.Number("-1"), json.Number("2.1"), []any{json.Number("3")}, map[string]any{"x": json.Number("3")}} {
		if scalarBounds(value, policy) == nil {
			t.Fatalf("out-of-range nested scalar accepted: %v", value)
		}
	}
	for _, bad := range []scalarPolicy{{Minimum: new("invalid")}, {Maximum: new("invalid")}} {
		if scalarBounds(json.Number("1"), bad) == nil {
			t.Fatal("invalid scalar bound definition accepted")
		}
	}
	if scalarBounds("not-a-number", policy) != nil {
		t.Fatal("numeric bounds changed a nonnumeric shape")
	}
	if childPolicy(nil).Minimum != nil || childPolicy(&policy).Minimum == nil {
		t.Fatal("optional child policy changed")
	}
}

package admission

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestConstraintEvaluationTypedPresenceAndClosure(t *testing.T) {
	validator, err := New()
	if err != nil {
		t.Fatal(err)
	}
	tests := []struct{ name, rule, actual, status string }{
		{"literal", `{"kind":"literal","value":1}`, `1`, "conformant"},
		{"strict boolean", `{"kind":"literal","value":true}`, `1`, "nonconformant"},
		{"strict numeric type", `{"kind":"literal","value":1}`, `1.0`, "nonconformant"},
		{"null", `{"kind":"literal","value":null}`, `null`, "conformant"},
		{"knowledge", `{"kind":"knowledge","state":"redacted"}`, `null`, "unresolved"},
		{"delegation", `{"kind":"delegated"}`, `{"choice":false}`, "conformant"},
		{"required", `{"kind":"recursive-record","fields":{"x":{"kind":"literal","value":null}}}`, `{}`, "nonconformant"},
		{"optional", `{"kind":"recursive-record","fields":{"x":{"kind":"literal","presence":"optional","value":null}}}`, `{}`, "conformant"},
		{"forbidden", `{"kind":"recursive-record","fields":{"x":{"kind":"literal","presence":"forbidden","value":null}}}`, `{"x":null}`, "nonconformant"},
		{"closed record", `{"kind":"recursive-record","fields":{}}`, `{"extra":0}`, "nonconformant"},
		{"sequence order", `{"kind":"sequence","items":[{"kind":"literal","value":1},{"kind":"literal","value":2}]}`, `[2,1]`, "nonconformant"},
		{"sequence extra", `{"kind":"sequence","items":[{"kind":"literal","value":1}]}`, `[1,2]`, "nonconformant"},
		{"nullable domain", `{"kind":"domain","domain":{"kind":"null"}}`, `null`, "conformant"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			constraint := constraintTestDocument(t, validator, test.rule)
			actual := constraintTestValue(t, validator, test.actual)
			result, err := EvaluateRealizationConstraint(constraint, actual, DefaultConstraintLimits())
			if err != nil {
				t.Fatal(err)
			}
			got := requireType[map[string]any](t, result.Document())
			if got["status"] != test.status {
				t.Fatalf("EvaluateRealizationConstraint() = %v, want %s", got, test.status)
			}
		})
	}
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func constraintTestDocument(t *testing.T, validator *Validator, rule string) Fragment {
	t.Helper()
	return constraintTestFragment(t, validator, RealizationConstraint, `{"semantic_profile":"test/v1","default_closure":{"posture":"closed","universe":"test","profile":"test/v1"},"root":`+rule+`}`)
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func constraintTestValue(t *testing.T, validator *Validator, actual string) Fragment {
	t.Helper()
	return constraintTestFragment(t, validator, RealizationValue, actual)
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func constraintTestFragment(t *testing.T, validator *Validator, profile FragmentProfile, raw string) Fragment {
	t.Helper()
	var value any
	// The test reader preserves JSON integer and floating-point categories.
	decoder := json.NewDecoder(strings.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		t.Fatal(err)
	}
	result, err := AdmitFragment(validator, profile, value, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64})
	if err != nil {
		t.Fatalf("AdmitFragment(%s): %v", profile, err)
	}
	return result
}

type replacedConstraintFragment struct{ Fragment }

func (replacedConstraintFragment) Profile() FragmentProfile { panic("foreign profile called") }
func (replacedConstraintFragment) Document() any            { panic("foreign document called") }

func TestConstraintOwnerChecksNativeFragments(t *testing.T) {
	validator, err := New()
	if err != nil {
		t.Fatal(err)
	}
	actual := constraintTestValue(t, validator, `null`)
	if err := CheckFragment(actual, RealizationValue); err != nil {
		t.Fatal(err)
	}
	for _, candidate := range []Fragment{nil, replacedConstraintFragment{actual}, actual} {
		if err := CheckFragment(candidate, RealizationConstraint); err == nil {
			t.Fatal("owner accepted a foreign or incorrectly profiled fragment")
		}
	}
}

func TestConstraintEvaluationLimitsAndForeignFragments(t *testing.T) {
	limits := DefaultConstraintLimits()
	if err := limits.Validate(); err != nil {
		t.Fatal(err)
	}
	limits.MaxNodes = 0
	if err := limits.Validate(); err == nil {
		t.Fatal("zero node budget accepted")
	}
	validator, err := New()
	if err != nil {
		t.Fatal(err)
	}
	constraint := constraintTestDocument(t, validator, `{"kind":"literal","value":"secret-value"}`)
	actual := constraintTestValue(t, validator, `"secret-value"`)
	limits = DefaultConstraintLimits()
	limits.MaxScalarBytes = 2
	result, err := EvaluateRealizationConstraint(constraint, actual, limits)
	if err != nil || requireType[map[string]any](t, result.Document())["status"] != "limit-exceeded" {
		t.Fatalf("exhausted relation = %v, %v", result, err)
	}
	if _, err := EvaluateRealizationConstraint(actual, constraint, DefaultConstraintLimits()); err == nil {
		t.Fatal("relation accepted reversed native fragment profiles")
	}
}

func TestConstraintNodeBudgetCountsSemanticNodes(t *testing.T) {
	validator, err := New()
	if err != nil {
		t.Fatal(err)
	}
	constraint := constraintTestDocument(t, validator, `{"kind":"literal","value":1}`)
	actual := constraintTestValue(t, validator, `1`)
	limits := DefaultConstraintLimits()
	limits.MaxNodes = 2
	result, err := EvaluateRealizationConstraint(constraint, actual, limits)
	if err != nil || requireType[map[string]any](t, result.Document())["status"] != "conformant" {
		t.Fatalf("two semantic nodes = %v, %v, want conformant", result, err)
	}
	limits.MaxNodes = 1
	result, err = EvaluateRealizationConstraint(constraint, actual, limits)
	if err != nil || requireType[map[string]any](t, result.Document())["status"] != "limit-exceeded" {
		t.Fatalf("one semantic node = %v, %v, want limit-exceeded", result, err)
	}
}

func TestConstraintKeyedIdentityAndAliases(t *testing.T) {
	validator, err := New()
	if err != nil {
		t.Fatal(err)
	}
	const rule = `{"kind":"keyed-collection","collection_kind":"test-records/v1","identity_fields":["id"],"members":[{"identity":["a"],"constraint":{"kind":"recursive-record","fields":{"id":{"kind":"literal","value":"a"},"value":{"kind":"literal","value":1}}}},{"identity":["b"],"constraint":{"kind":"recursive-record","fields":{"id":{"kind":"literal","value":"b"},"value":{"kind":"literal","value":2}}}}],"aliases":[{"identity":["old-a"],"target":["a"]}]}`
	constraint := constraintTestDocument(t, validator, rule)
	for _, test := range []struct{ actual, status string }{
		{`[{"id":"b","value":2},{"id":"a","value":1}]`, "conformant"},
		{`[{"id":"old-a","value":1},{"id":"b","value":2}]`, "conformant"},
		{`[{"id":"a","value":1},{"id":"old-a","value":1},{"id":"b","value":2}]`, "invalid"},
		{`[{"value":1},{"id":"b","value":2}]`, "invalid"},
		{`[{"id":"a","value":1}]`, "nonconformant"},
	} {
		result, err := EvaluateRealizationConstraint(constraint, constraintTestValue(t, validator, test.actual), DefaultConstraintLimits())
		if err != nil || requireType[map[string]any](t, result.Document())["status"] != test.status {
			t.Fatalf("keyed relation = %v, %v, want %s", result, err, test.status)
		}
	}
}

func TestConstraintScopesApplyThroughDelegation(t *testing.T) {
	validator, err := New()
	if err != nil {
		t.Fatal(err)
	}
	constraint := constraintTestFragment(t, validator, RealizationConstraint, `{"semantic_profile":"test/v1","default_closure":{"posture":"open","universe":"test","profile":"test/v1"},"root":{"kind":"delegated"},"scopes":[{"field_pointer":"/child","closure":{"posture":"closed","universe":"child","profile":"test/v1"}}]}`)
	for _, test := range []struct{ actual, status string }{
		{`{"child":{}}`, "conformant"},
		{`{"child":{"extra":1}}`, "nonconformant"},
		{`{"child":1}`, "unsupported"},
		{`{"other":true}`, "conformant"},
	} {
		result, err := EvaluateRealizationConstraint(constraint, constraintTestValue(t, validator, test.actual), DefaultConstraintLimits())
		if err != nil || requireType[map[string]any](t, result.Document())["status"] != test.status {
			t.Fatalf("scoped relation = %v, %v, want %s", result, err, test.status)
		}
	}
}

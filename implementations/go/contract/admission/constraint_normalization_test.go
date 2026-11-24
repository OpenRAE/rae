package admission

import (
	"strings"
	"testing"
)

func TestConstraintNormalizationRetainsIdentityScopeAndPresence(t *testing.T) {
	v, err := New()
	if err != nil {
		t.Fatal(err)
	}
	input := constraintTestValue(t, v, `[{"name":"b","value":2},{"name":"a","value":1}]`)
	closure := RealizationClosure{Posture: "closed", Universe: "test", Profile: "test/v1"}
	metadata := RealizationNormalizationMetadata{
		CollectionProfiles: []RealizationCollectionProfile{{FieldPointer: "", CollectionKind: "test", IdentityFields: []string{"name"}, Closure: closure}},
		Scopes:             []RealizationScope{{FieldPointer: "/0", Closure: RealizationClosure{Posture: "open", Universe: "test", Profile: "test/v1"}}},
		OptionalFields:     []string{"/0/value"}, Origins: map[string]string{"/0/value": "default"},
		LeafConstraints: map[string]Fragment{"/1/value": constraintTestValue(t, v, `{"kind":"domain","domain":{"kind":"enum","values":[1,3]}}`)},
	}
	result, err := NormalizeRealizationLiteral(input, "test/v1", closure, metadata, DefaultConstraintLimits())
	if err != nil || result.Status != "conformant" {
		t.Fatalf("normalize: %+v %v", result, err)
	}
	document := requireType[map[string]any](t, result.Document.Document())
	scope := requireType[string](t, requireType[map[string]any](t, requireType[[]any](t, document["scopes"])[0])["field_pointer"])
	if !strings.HasPrefix(scope, "/@sha256:") {
		t.Fatalf("source scope not converted: %s", scope)
	}
	for _, raw := range []string{`[{"name":"a","value":3},{"name":"b","extra":true}]`, `[{"name":"b","value":2},{"name":"a","value":1}]`} {
		got, checkErr := EvaluateRealizationConstraint(result.Document, constraintTestValue(t, v, raw), DefaultConstraintLimits())
		if checkErr != nil || requireType[map[string]any](t, got.Document())["status"] != "conformant" {
			t.Fatalf("normalized relation: %v %v", got, checkErr)
		}
	}
	first, err := RealizationConstraintBinding(result.Document, input)
	if err != nil {
		t.Fatal(err)
	}
	second, err := RealizationConstraintBinding(result.Document, constraintTestValue(t, v, `[{"name":"b","value":3},{"name":"a","value":1}]`))
	if err != nil || first == second || !strings.HasPrefix(first, "sha256:") {
		t.Fatalf("binding does not cover source: %q %q %v", first, second, err)
	}
}

func TestConstraintNormalizationRefusesAmbiguityAndUnresolvedMetadata(t *testing.T) {
	v, err := New()
	if err != nil {
		t.Fatal(err)
	}
	closure := RealizationClosure{Posture: "closed", Universe: "test", Profile: "test/v1"}
	tests := []struct {
		name, raw string
		metadata  RealizationNormalizationMetadata
		status    string
	}{
		{"duplicate identity", `[{"name":"a"},{"name":"a"}]`, RealizationNormalizationMetadata{CollectionProfiles: []RealizationCollectionProfile{{CollectionKind: "test", IdentityFields: []string{"name"}, Closure: closure}}}, "invalid"},
		{"missing metadata path", `{"a":1}`, RealizationNormalizationMetadata{OptionalFields: []string{"/absent"}}, "invalid"},
		{"non scalar leaf", `{"a":[]}`, RealizationNormalizationMetadata{LeafConstraints: map[string]Fragment{"/a": constraintTestValue(t, v, `{"kind":"delegated"}`)}}, "invalid"},
		{"invalid leaf shape", `{"a":1}`, RealizationNormalizationMetadata{LeafConstraints: map[string]Fragment{"/a": constraintTestValue(t, v, `{"kind":"literal","value":1,"extra":true}`)}}, "invalid"},
		{"unused invalid collection", `1`, RealizationNormalizationMetadata{CollectionProfiles: []RealizationCollectionProfile{{CollectionKind: "test", Closure: closure}}}, "invalid"},
		{"undefined collection closure", `[]`, RealizationNormalizationMetadata{CollectionProfiles: []RealizationCollectionProfile{{CollectionKind: "test", IdentityFields: []string{"name"}}}}, "invalid"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, checkErr := NormalizeRealizationLiteral(constraintTestValue(t, v, tt.raw), "test/v1", closure, tt.metadata, DefaultConstraintLimits())
			if checkErr != nil || result.Status != tt.status || result.Document != nil || len(result.Diagnostics) != 1 {
				t.Fatalf("normalization: %+v %v", result, checkErr)
			}
		})
	}
	input := constraintTestValue(t, v, `{"a":1}`)
	limits := DefaultConstraintLimits()
	limits.MaxNodes = 1
	result, err := NormalizeRealizationLiteral(input, "test/v1", closure, RealizationNormalizationMetadata{}, limits)
	if err != nil || result.Status != "limit-exceeded" {
		t.Fatalf("node exhaustion: %+v %v", result, err)
	}
	if _, err := NormalizeRealizationLiteral(replacedConstraintFragment{input}, "test/v1", closure, RealizationNormalizationMetadata{}, DefaultConstraintLimits()); err == nil {
		t.Fatal("foreign input accepted")
	}
	if _, err := NormalizeRealizationLiteral(input, "test/v1", closure, RealizationNormalizationMetadata{LeafConstraints: map[string]Fragment{"/a": replacedConstraintFragment{input}}}, DefaultConstraintLimits()); err == nil {
		t.Fatal("foreign metadata accepted")
	}
}

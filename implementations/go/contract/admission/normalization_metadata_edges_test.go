package admission

import (
	"strings"
	"testing"
)

func TestNormalizationMetadataBudgetsRefuseEveryAuthorityCarrier(t *testing.T) {
	owner := boundTestOwner(t)
	input := constraintTestValue(t, owner, `{}`)
	large := strings.Repeat("x", 65)
	for _, test := range []struct {
		name     string
		metadata RealizationNormalizationMetadata
	}{
		{"scope", RealizationNormalizationMetadata{Scopes: []RealizationScope{{FieldPointer: "/" + large}}}},
		{"origin", RealizationNormalizationMetadata{Origins: map[string]string{"": large}}},
		{"optional", RealizationNormalizationMetadata{OptionalFields: []string{"/" + large}}},
		{"presence", RealizationNormalizationMetadata{MemberPresence: map[string]string{"/" + large: "required"}}},
	} {
		t.Run(test.name, func(t *testing.T) {
			limits := DefaultConstraintLimits()
			limits.MaxScalarBytes = 64
			result, err := NormalizeRealizationLiteral(input, "test/v1", RealizationClosure{Posture: "open"}, test.metadata, limits)
			if err != nil || result.Status != "limit-exceeded" || result.Document != nil {
				t.Fatalf("metadata budget admitted partial authority: %+v %v", result, err)
			}
		})
	}
	limits := DefaultConstraintLimits()
	limits.MaxMembers = 1
	result, err := NormalizeRealizationLiteral(input, "test/v1", RealizationClosure{Posture: "open"}, RealizationNormalizationMetadata{OptionalFields: []string{"/a", "/b"}}, limits)
	if err != nil || result.Status != "limit-exceeded" || result.Document != nil {
		t.Fatal("metadata member ceiling ignored")
	}
}

func TestNormalizationCollectionProfilesRefuseAmbiguousIdentityAndPresence(t *testing.T) {
	owner := boundTestOwner(t)
	input := constraintTestValue(t, owner, `{"items":[{"name":"a"}]}`)
	profile := RealizationCollectionProfile{FieldPointer: "/items", CollectionKind: "test-item", IdentityFields: []string{"name"}, Closure: RealizationClosure{Posture: "open"}}
	for _, test := range []struct {
		name     string
		metadata RealizationNormalizationMetadata
	}{
		{"duplicate profiles", RealizationNormalizationMetadata{CollectionProfiles: []RealizationCollectionProfile{profile, profile}}},
		{"invalid pointer", RealizationNormalizationMetadata{CollectionProfiles: []RealizationCollectionProfile{{FieldPointer: "items", Closure: profile.Closure}}}},
		{"invalid closure", RealizationNormalizationMetadata{CollectionProfiles: []RealizationCollectionProfile{{FieldPointer: "/items", Closure: RealizationClosure{Posture: "invented"}}}}},
		{"unknown presence", RealizationNormalizationMetadata{MemberPresence: map[string]string{"/items": "invented"}}},
		{"missing optional field", RealizationNormalizationMetadata{OptionalFields: []string{"/missing"}}},
		{"duplicate scopes", RealizationNormalizationMetadata{Scopes: []RealizationScope{{FieldPointer: "/items", Closure: profile.Closure}, {FieldPointer: "/items", Closure: profile.Closure}}}},
	} {
		t.Run(test.name, func(t *testing.T) {
			result, err := NormalizeRealizationLiteral(input, "test/v1", RealizationClosure{Posture: "open"}, test.metadata, DefaultConstraintLimits())
			if err != nil || result.Status != "invalid" || result.Document != nil {
				t.Fatalf("ambiguous metadata admitted: %+v %v", result, err)
			}
		})
	}
}

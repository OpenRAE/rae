package authoring

import (
	"encoding/json"
	"slices"
	"testing"
)

func TestLegacyMigrationPresenceKeepsNativeScalarAndCollectionMeaning(t *testing.T) {
	for _, test := range []struct {
		value   any
		present bool
	}{
		{nil, false}, {false, false}, {true, true}, {"", false}, {"value", true},
		{[]any{}, false}, {[]any{false}, true}, {map[string]any{}, false}, {map[string]any{"value": false}, true},
		{json.Number("0e2"), false}, {json.Number("-1"), true}, {json.Number("0.01"), true},
	} {
		if nonemptyJSON(test.value) != test.present {
			t.Fatalf("legacy migration changed native presence for %v", test.value)
		}
	}
}

func TestEnumConstructionKeepsUnionMembersAndBoundsRecursiveMetadata(t *testing.T) {
	walk := normalizer{parser: operationParser(t), id: authoringContract}
	schema := map[string]any{"enum": []any{"one"}, "anyOf": []any{map[string]any{"enum": []any{"two"}}, map[string]any{"enum": []any{"three"}}}}
	if got := walk.enumMembers(schema, 0); !slices.Equal(got, []any{"one", "two", "three"}) {
		t.Fatalf("enum union lost native members: %+v", got)
	}
	for range 17 {
		schema = map[string]any{"anyOf": []any{schema}}
	}
	if got := walk.enumMembers(schema, 0); len(got) != 0 {
		t.Fatal("over-depth enum metadata produced partial membership authority")
	}
}

func TestParticipantMigrationContextRefusesMalformedUnboundDecisions(t *testing.T) {
	p := operationParser(t)
	for _, raw := range []string{`{`, `[]`, `{}`, `{"source_digest":"invalid"}`, `{"source_digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000","entity_objectives":true}`} {
		if _, err := p.participantContext([]byte(raw)); err == nil {
			t.Fatal("unbound participant migration decisions accepted")
		}
	}
	if context, err := p.participantContext([]byte(`null`)); err != nil || context != nil {
		t.Fatal("absent participant decisions invented migration authority")
	}
}

func TestClassificationMigrationRequiresExplicitCanonicalLossPolicy(t *testing.T) {
	p := operationParser(t)
	for _, raw := range []string{`[]`, `{"extra":true}`, `{"bindings":true}`, `{"policy":true}`, `{"policy":{"allowed_loss_kinds":null}}`, `{"policy":{"allowed_loss_kinds":["unknown"]}}`, `{"policy":{"allowed_loss_kinds":["semantic-omission","declaration-removed"]}}`, `{"policy":{"allowed_loss_kinds":["semantic-omission","semantic-omission"]}}`} {
		if _, err := p.classificationContext([]byte(raw)); err == nil {
			t.Fatal("invalid classification loss authority accepted")
		}
	}
	if context, err := p.classificationContext([]byte(`null`)); err != nil || context == nil || len(context.allowed) != 0 {
		t.Fatal("default classification context granted loss permission")
	}
}

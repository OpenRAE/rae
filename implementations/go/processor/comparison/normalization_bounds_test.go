package comparison

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestComparisonResultBudgetsRefuseEveryOutputAuthorityCarrier(t *testing.T) {
	large := strings.Repeat("x", 1<<20+1)
	for _, output := range []result{
		{Schema: large}, {Scope: scope{ID: large}}, {Scope: scope{Roots: []string{large}}},
		{Scope: scope{Before: []coordinate{{Identity: large}}}}, {Before: coordinate{Identity: large}},
		{Changes: []change{{Identity: large}}}, {Changes: []change{{Reasons: []string{large}}}},
		{Dependencies: []dependencyChange{{Dependent: large}}}, {Dependencies: []dependencyChange{{Before: &dependencyState{Identity: large}}}},
		{Paths: []impactPath{{Source: large}}}, {Paths: []impactPath{{Steps: []pathStep{{Dependent: large}}}}},
		{Reasons: []string{large}},
	} {
		if boundResult(output) == nil {
			t.Fatal("comparison output exceeded a native scalar bound")
		}
	}
	budget := wireBudget{remaining: 1}
	if budget.record(0, "escaped\nvalue") == nil {
		t.Fatal("escaped JSON bytes did not consume the aggregate budget")
	}
	budget = wireBudget{remaining: 100, visits: 100000}
	if budget.record(0) == nil {
		t.Fatal("comparison record visit bound ignored")
	}
}

func TestComparisonNormalizationRefusesUnknownModelsAndExhaustedWork(t *testing.T) {
	if _, err := normalizeOwner("unknown", map[string]any{}); err == nil {
		t.Fatal("unknown comparison model accepted")
	}
	if _, err := normalizeOwner("unknown", true); err == nil {
		t.Fatal("scalar comparison model accepted")
	}
	rules := normalizationMetadata{Models: map[string]normalizationModel{"child": {Fields: map[string]normalizationField{"created": {Factory: json.RawMessage(`true`)}}}}}
	for _, test := range []struct {
		rule  normalizationChild
		input any
		depth int
	}{
		{normalizationChild{Model: "child"}, map[string]any{}, 65},
		{normalizationChild{Items: &normalizationChild{Model: "child"}}, []any{map[string]any{}}, 0},
		{normalizationChild{Values: &normalizationChild{Model: "child"}}, map[string]any{"entry": map[string]any{}}, 0},
	} {
		work := normalizationWork{rules: rules, remaining: 1}
		if work.child(test.rule, test.input, test.depth) == nil {
			t.Fatal("native normalization ignored its work or depth bound")
		}
	}
}

func TestComparisonNormalizationCannotMatchMissingOrMalformedDiscriminators(t *testing.T) {
	rule := normalizationModel{Required: []string{"kind"}, Literals: map[string][]json.RawMessage{"kind": {json.RawMessage(`"known"`)}}}
	work := normalizationWork{rules: normalizationMetadata{Models: map[string]normalizationModel{"typed": rule}}, remaining: 100}
	for _, input := range []any{true, map[string]any{}, map[string]any{"kind": "other"}, map[string]any{"kind": func() {}}} {
		if work.matches(normalizationChild{Model: "typed"}, input) {
			t.Fatal("invalid comparison discriminator selected a model")
		}
	}
	if !work.matches(normalizationChild{Items: &normalizationChild{}}, []any{}) || !work.matches(normalizationChild{Values: &normalizationChild{}}, map[string]any{}) {
		t.Fatal("native collection alternatives lost their shape")
	}
}

func TestComparisonNormalizationRefusesCorruptFactoriesAndIncompleteChildWork(t *testing.T) {
	for _, test := range []struct {
		rule      normalizationField
		input     map[string]any
		remaining int
	}{
		{normalizationField{Factory: json.RawMessage(`{`)}, map[string]any{}, 100},
		{normalizationField{Omit: json.RawMessage(`null`)}, map[string]any{"value": func() {}}, 100},
		{normalizationField{Child: &normalizationChild{Model: "unknown"}}, map[string]any{"value": map[string]any{}}, 100},
		{normalizationField{}, map[string]any{}, 0},
	} {
		work := normalizationWork{remaining: test.remaining}
		if work.field("value", test.rule, test.input, 0) == nil {
			t.Fatal("corrupt comparison defaults or partial child work accepted")
		}
	}
}

func TestComparisonContextRequiresSortedUniqueValidEvidenceDigests(t *testing.T) {
	for _, digests := range [][]string{{"invalid"}, {"a", "a"}, {"z", "a"}, make([]string, 4097)} {
		if _, err := admitContext(Options{EvidenceDigests: digests}); err == nil {
			t.Fatal("ambiguous comparison context evidence accepted")
		}
	}
	if _, err := hash(func() {}); err == nil {
		t.Fatal("non-JSON comparison evidence produced a digest")
	}
}

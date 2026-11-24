package analysis

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestOpacityModelUnsupportedFindingsAreSortedByAddress(t *testing.T) {
	input := map[string]any{
		"complete_model":   false,
		termDeclaredCounts: map[string]any{termStates: json.Number("4097")},
		termAssumptions:    map[string]any{termSchedulerRefs: []any{}, termEnvironmentRefs: []any{"e"}, "order_treatment": "partial-order"},
	}
	codes := []string{}
	for _, finding := range opacityModelUnsupported(input) {
		codes = append(codes, finding.Address+" "+finding.Code)
	}
	expected := []string{
		"/assumptions participant-opacity-model-check.unsupported-scheduler-quantification",
		"/assumptions/order_treatment participant-opacity-model-check.unsupported-order-treatment",
		"/complete_model participant-opacity-model-check.incomplete-model",
		"/declared_counts participant-opacity-model-check.bound-exceeded",
	}
	if len(codes) != len(expected) {
		t.Fatalf("got %v, want %v", codes, expected)
	}
	for index := range expected {
		if codes[index] != expected[index] {
			t.Fatalf("got %v, want %v", codes, expected)
		}
	}
}

func TestOpacityCatalogRequiresTheGovernedCatalog(t *testing.T) {
	if err := admitOpacityCatalog(map[string]any{}, &JSONInput{Catalog: satisfiabilityEvidenceValue(t)}); err == nil {
		t.Fatal("got nil error, want a foreign catalog refused")
	}
	if _, err := packagedOpacityCatalog("no-such-revision"); err == nil {
		t.Fatal("got nil error, want an unknown revision refused")
	}
}

func TestOpacityModelAssumptionsMustMatchTheProfile(t *testing.T) {
	passive := map[string]any{termParameters: map[string]any{termStrategy: map[string]any{termKind: "fixed"}}}
	twoStrategies := map[string]any{termAssumptions: map[string]any{termStrategyRefs: []any{"a", "b"}}}
	requireCategory(t, admitModelAssumptions(twoStrategies, passive, nil), fault.Operational)
	active := map[string]any{termParameters: map[string]any{termStrategy: map[string]any{termKind: "active", termStrategyRefs: []any{"a"}}}}
	requireCategory(t, admitModelAssumptions(map[string]any{termAssumptions: map[string]any{}}, active, nil), fault.Operational)
}

func TestOpacityInitialDomainMustCoverEveryProfileCombination(t *testing.T) {
	input := map[string]any{"initial_state_ordinals": []any{json.Number("0")}}
	parameters := map[string]any{
		termSchedulerRefs:   []any{"s1", "s2"},
		termEnvironmentRefs: []any{"e"},
		termOrder:           map[string]any{termOrderRefs: []any{"o"}},
	}
	points := []opacityPoint{{Strategy: "a", Scheduler: "s1", Environment: "e", Order: "o"}}
	requireCategory(t, admitInitialOpacityDomain(input, parameters, points, []any{"a"}), fault.Operational)
}

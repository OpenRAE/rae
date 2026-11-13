package admission

import (
	"slices"
	"testing"
)

func observationPolicyState() *observationNormalizer {
	return &observationNormalizer{limits: DefaultConstraintLimits()}
}

func TestIndependentObservationAuthoritiesReportStableAxisConflicts(t *testing.T) {
	for _, scope := range []string{"", "/nodes/host"} {
		n := observationPolicyState()
		rules := []observationRule{
			{ID: "second", Authority: "z-authority", Mode: new("selected"), Scope: scope},
			{ID: "first", Authority: "a-authority", Mode: new("none"), Scope: scope},
		}
		mode, origin := n.axis(rules, "mode", "none", scope)
		if mode != "none" || origin != "first,second" || len(n.diagnostics) != 1 {
			t.Fatalf("unstable authority join: %q %q %+v", mode, origin, n.diagnostics)
		}
		finding := n.diagnostics[0]
		if finding.Code != "observation.authority-conflict" || finding.Severity != "error" || finding.Address == "" {
			t.Fatalf("invalid conflict finding: %+v", finding)
		}
		n.limits.MaxDiagnostics = 1
		n.conflict(scope, "collection", rules)
		if len(n.diagnostics) != 1 {
			t.Fatal("diagnostic ceiling ignored")
		}
	}
}

type observationLifecycleCase struct {
	name, mode, collection, retention, export string
	selected                                  bool
	wantMode                                  string
	conflicts                                 int
}

func TestObservationLifecycleNeverExportsUncollectedOrUnselectedData(t *testing.T) {
	for _, test := range []observationLifecycleCase{
		{"none with selector", "none", "require", "require", "require", true, "none", 1},
		{"selected without selector", "selected", "require", "disable", "disable", false, "none", 1},
		{"exhaustive without selector", "exhaustive", "require", "disable", "disable", false, "none", 1},
		{"retention without collection", "selected", "disable", "require", "disable", true, "selected", 1},
		{"export without collection", "selected", "disable", "disable", "require", true, "selected", 1},
		{"selected collection", "selected", "require", "require", "require", true, "selected", 0},
	} {
		t.Run(test.name, func(t *testing.T) {
			checkObservationLifecycle(t, test)
		})
	}
}

func checkObservationLifecycle(t *testing.T, test observationLifecycleCase) {
	t.Helper()
	n := observationPolicyState()
	selectors := []observationSelector{}
	if test.selected {
		selectors = append(selectors, observationSelector{Scope: "/nodes/host", Kind: "stream", Names: []string{"events"}})
	}
	values := map[string]string{"collection": test.collection, "retention": test.retention, "export": test.export}
	mode, got := n.lifecycle(test.mode, selectors, values, "/nodes/host", nil)
	if mode != test.wantMode || len(n.diagnostics) != test.conflicts {
		t.Fatalf("lifecycle=%q conflicts=%+v", mode, n.diagnostics)
	}
	if test.conflicts > 0 && (values["collection"] != "disable" || values["retention"] != "disable" || values["export"] != "disable") {
		t.Fatalf("unsafe lifecycle retained: %v", values)
	}
	if mode == "none" && len(got) > 0 {
		t.Fatal("none retained selectors")
	}
}

func TestOverlappingObservationSelectorsRespectIndependentLifecycleProhibitions(t *testing.T) {
	selector := observationSelector{Scope: "/nodes/host", Kind: "stream", Names: []string{"events"}, Components: []string{"observer"}}
	for _, axis := range []string{"collection", "retention", "export"} {
		t.Run(axis, func(t *testing.T) {
			checkObservationAxisOverlap(t, selector, axis)
		})
	}
	for _, changed := range []observationSelector{
		{Scope: "/other", Kind: "stream", Names: []string{"events"}},
		{Scope: selector.Scope, Kind: "file", Names: []string{"events"}},
		{Scope: selector.Scope, Kind: "stream", Names: []string{"other"}},
		{Scope: selector.Scope, Kind: "stream", Names: selector.Names, Components: []string{"other"}},
		{Scope: selector.Scope, Kind: "stream", Names: selector.Names, Excluded: []string{selector.Scope}},
	} {
		if observationSelectorOverlap(selector, changed) {
			t.Fatalf("disjoint selector overlaps: %+v", changed)
		}
	}
	n := observationPolicyState()
	n.limits.MaxOperations = 1
	if n.selectorsOverlap([]observationSelector{selector, selector}, []observationSelector{selector}) {
		t.Fatal("exhausted overlap search returned authority")
	}
}

func checkObservationAxisOverlap(t *testing.T, selector observationSelector, axis string) {
	t.Helper()
	n := observationPolicyState()
	a := observationEffective{Scope: "/nodes/host", Selectors: []observationSelector{selector}, Collection: "require", Retention: "require", Export: "require"}
	b := a
	b.Prohibited = []string{axis}
	if !n.overlapConflict(a, b, nil, nil) || !n.overlapConflict(b, a, nil, nil) {
		t.Fatal("independent prohibition did not conflict in both orders")
	}
	n.scopeConflicts([]observationEffective{a, b}, [][]observationRule{nil, nil}, a.Scope, nil)
	if len(n.diagnostics) != 1 {
		t.Fatal("overlap did not produce exactly one finding")
	}
	a.Required = true
	b.Required = true
	b.Prohibited = nil
	rules := []observationRule{{ID: "mandatory", Required: true, Collection: new("disable"), Retention: new("disable"), Export: new("disable")}}
	a.Collection = "disable"
	a.Retention = "disable"
	a.Export = "disable"
	if !n.overlapAxisConflict(a, b, rules, rules, axis) || !n.overlapAxisConflict(b, a, rules, rules, axis) {
		t.Fatal("contradictory mandatory lifecycle was accepted")
	}
	if n.overlapAxisConflict(a, b, nil, nil, axis) {
		t.Fatal("undeclared axis became mandatory")
	}
}

func TestObservationSpecificityAndMandatoryRulesKeepIndependentAuthority(t *testing.T) {
	rules := []observationRule{
		{ID: "parent", Scope: "", Mode: new("selected"), Authority: "author"},
		{ID: "child", Scope: "/nodes/host", Mode: new("none"), Authority: "author"},
		{ID: "mandatory", Scope: "", Mode: new("none"), Required: true, Authority: "privacy"},
	}
	n := observationPolicyState()
	chosen, forbidden := n.candidates(rules, "mode")
	if len(chosen) != 1 || chosen[0].ID != "mandatory" || len(forbidden) != 0 {
		t.Fatal("mandatory rule lost to specificity")
	}
	withoutMandatory := n.effectiveRules(rules[:2], "none")
	if len(withoutMandatory) != 1 || withoutMandatory[0].ID != "child" {
		t.Fatalf("specific rule not selected: %+v", withoutMandatory)
	}
	prohibited, required := observationProhibitions([]observationRule{{Required: true, Collection: new("forbid"), Retention: new("forbid"), Export: new("forbid"), Prohibited: []string{"collection"}}})
	if !required || !slices.Equal(prohibited, []string{"collection", "export", "retention"}) {
		t.Fatalf("lost prohibitions: %v", prohibited)
	}
	selected := observationRule{ID: "selector", Authority: "author", Scope: "/nodes/host", Selector: &observationSelector{Scope: "/nodes/host", Kind: "stream", Names: []string{"events"}}}
	policy := n.selectedPolicy(append(rules, selected), selected)
	if len(policy) != 4 {
		t.Fatalf("lost inherited or independent policy: %+v", policy)
	}
}

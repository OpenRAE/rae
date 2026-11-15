package admission

import (
	"encoding/json"
	"slices"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestTrialSourceOrderRefusesMalformedDocumentsAndPreservesNestedMembers(t *testing.T) {
	for _, test := range []struct{ name, source, target string }{
		{"empty", "", "/entries"}, {"relative", `{}`, "entries"}, {"truncated-object", `{"entries":{"a":1`, "/entries"}, {"truncated-array", `{"items":[{"entries":{"a":1}}`, "/items/0/entries"}, {"trailing-document", `{"entries":{}} {}`, "/entries"}, {"closing-token", `}`, "/entries"}, {"depth", strings.Repeat(`[`, 65) + `0` + strings.Repeat(`]`, 65), "/entries"},
	} {
		t.Run(test.name, func(t *testing.T) {
			if _, err := trialSourceMemberOrder(test.source, test.target); err == nil {
				t.Fatal("ambiguous or unbounded member order admitted")
			}
		})
	}
	order, err := trialSourceMemberOrder(`{"ignored":[],"items":[{"entries":{"z":{},"a":{}}}]}`, "/items/0/entries")
	if err != nil || !slices.Equal(order, []string{"z", "a"}) {
		t.Fatal("nested source member order changed", order, err)
	}
	for _, order := range [][]string{nil, {"a", "a"}, {"a", "foreign"}} {
		if _, err := trialOrderedJSON(map[string]any{"entries": map[string]any{"a": map[string]any{}, "b": map[string]any{}}}, order); err == nil {
			t.Fatal("incomplete entry order admitted")
		}
	}
	owner := boundTestOwner(t)
	for _, raw := range []string{`{"entries":{"a":null}}`, `{"entries":{"a":{}}}`, `{"entries":{},"cleanup_plans":{"c":{}}}`} {
		if _, err := SealTrialPlan(owner, []byte(raw), ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}); err == nil {
			t.Fatal("unconstructable trial member sealed")
		}
	}
}
func TestStudyPlanRequiresExactDefinitionMembershipAndAllocationBounds(t *testing.T) {
	for _, test := range []struct {
		name, plan, study string
		valid             bool
	}{
		{"unbound", `{}`, `{}`, true},
		{"exact-definition", `{"input_refs":{"study_ref":{"ref_id":"s","ref_version":"1"}}}`, `{"study_id":"s","study_version":"snapshot","definition_ref":{"ref_version":"1"}}`, true},
		{"foreign-definition", `{"input_refs":{"study_ref":{"ref_id":"s","ref_version":"2"}}}`, `{"study_id":"s","study_version":"snapshot","definition_ref":{"ref_version":"1"}}`, false},
		{"missing-evaluation-membership", `{}`, `{"membership":{}}`, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			runs := []any{}
			if test.name == "missing-evaluation-membership" {
				runs = append(runs, map[string]any{"run_id": "r", "trial_provenance": map[string]any{}})
			}
			if err := studyPlanIdentity(decodeRuleObject(t, test.plan), decodeRuleObject(t, test.study), runs); (err == nil) != test.valid {
				t.Fatal("study identity admission", err)
			}
		})
	}
	plan := decodeRuleObject(t, `{"entries":{"one":{"coordinate":{"condition_id":"c"}},"two":{"coordinate":{"condition_id":"c"}}}}`)
	for _, test := range []struct {
		study string
		valid bool
	}{
		{`{"run_allocation":{"condition_assignments":{"c":{}},"target_runs_per_condition":2}}`, true},
		{`{"run_allocation":{"condition_assignments":{"c":{}},"target_runs_per_condition":1}}`, false},
		{`{"run_allocation":{"condition_assignments":{},"target_runs_per_condition":2}}`, false},
	} {
		if err := studyPlanAllocation(plan, decodeRuleObject(t, test.study)); (err == nil) != test.valid {
			t.Fatal("study allocation admission", err)
		}
	}
}
func TestTypedTreatmentSelectionsCannotConflictWithBindingsOrSourceLevels(t *testing.T) {
	selection := `{"selection_id":"s","source_factor_id":"f","source_factor_level_id":"one","target":{"scenario_family_id":"family","variation_point_id":"point"}}`
	for _, test := range []struct {
		name, entry string
		selections  string
		levels      map[string]string
		valid       bool
	}{
		{"exact", `{}`, `[` + selection + `]`, map[string]string{}, true},
		{"duplicate-id", `{}`, `[` + selection + `,` + selection + `]`, map[string]string{}, false},
		{"binding-point-conflict", `{"bindings":[{"descriptor":{"target":{"plane":"scenario","scenario_family_id":"family","variation_point_id":"point"}}}]}`, `[` + selection + `]`, map[string]string{}, false},
		{"factor-level-conflict", `{}`, `[` + selection + `]`, map[string]string{"f": "two"}, false},
		{"binding-level-conflict", `{"bindings":[{"descriptor":{"source_factor_id":"f","source_factor_level_id":"two"}}]}`, `[` + selection + `]`, map[string]string{}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			var selections []any
			if json.Unmarshal([]byte(test.selections), &selections) != nil {
				t.Fatal("treatment fixture")
			}
			if err := trialTreatmentSelections(decodeRuleObject(t, test.entry), selections, test.levels); (err == nil) != test.valid {
				t.Fatal("treatment consistency admission", err)
			}
		})
	}
	plan := decodeRuleObject(t, `{"input_refs":{"scenario_family_ref":{"ref_id":"family"}}}`)
	for _, binding := range []string{`{"descriptor":{"source_condition_id":"other"}}`, `{"descriptor":{"source_condition_id":"c","target":{"plane":"scenario","scenario_family_id":"other"}}}`} {
		if err := trialTreatmentBinding(plan, decodeRuleObject(t, `{"coordinate":{"condition_id":"c"}}`), decodeRuleObject(t, binding), map[string]bool{}, map[string]string{}); err == nil {
			t.Fatal("foreign treatment source admitted")
		}
	}
	if err := trialEntryTreatments(plan, decodeRuleObject(t, `{"selections":[{"origin_policy_id":"factorial-treatments-v1","origin_policy_kind":"stratified","variation_point_id":"unbound"}]}`)); err == nil {
		t.Fatal("unbound factorial selection admitted")
	}
}

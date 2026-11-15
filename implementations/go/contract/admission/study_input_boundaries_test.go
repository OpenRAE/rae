package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func replacementStudyBoundaryInputs(t *testing.T, owner *Validator, reference replacementStudyReference) TrialStudyInputs {
	t.Helper()
	structural := schemaOnlyTestOwner(t, owner)
	value := func(id string, raw []byte) validation.Value {
		t.Helper()
		admitted, err := structural.Validate(id, raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
		if err != nil {
			t.Fatal(err)
		}
		return admitted
	}
	input := TrialStudyInputs{Plan: value(trialPlanContract, reference.Root), Study: value(contractExperimentStudy, reference.Study)}
	for _, raw := range reference.Tasks {
		input.Tasks = append(input.Tasks, value(termExperimentTaskV1, raw))
	}
	for _, raw := range reference.Runs {
		input.Runs = append(input.Runs, value(termExperimentRunV1, raw))
	}
	for _, raw := range reference.Plans {
		input.ReplacementPlans = append(input.ReplacementPlans, value(trialPlanContract, raw))
	}
	for _, raw := range reference.Receipts {
		input.CleanupReceipts = append(input.CleanupReceipts, value(termTrialCleanupReceiptV1, raw))
	}
	input.EvidenceByRun = replacementStudyEvidence(t, reference, value)
	return input
}
func TestReplacementStudyRefusesUnownedInputsAtEveryAuthorityBoundary(t *testing.T) {
	owner := boundTestOwner(t)
	var reference replacementStudyReference
	readFullReferenceJSON(t, "testdata/replacement-study-reference.json", &reference)
	for _, field := range []string{"plan", "study", "task", "run", "child", "cleanup"} {
		t.Run(field, func(t *testing.T) {
			input := replacementStudyBoundaryInputs(t, owner, reference)
			switch field {
			case "plan":
				input.Plan = validation.Value{}
			case "study":
				input.Study = validation.Value{}
			case "task":
				input.Tasks = []validation.Value{{}}
			case "run":
				input.Runs = []validation.Value{{}}
			case "child":
				input.ReplacementPlans = []validation.Value{{}}
			case "cleanup":
				input.CleanupReceipts = []validation.Value{{}}
			}
			if err := ValidateTrialStudy(owner, input); err == nil {
				t.Fatal("unowned study input admitted")
			}
		})
	}
}
func TestReplacementHistoryRefusesForeignRootsIdentitiesAndSupersededVersions(t *testing.T) {
	owner := boundTestOwner(t)
	root := decodeRuleObject(t, `{"replacement_origin":{}}`)
	if _, err := owner.replacementStudyRuns(root, nil, nil, nil); err == nil {
		t.Fatal("child plan used as replacement root")
	}
	for _, test := range []struct {
		name  string
		plans map[string]any
	}{
		{"entry-id", map[string]any{"a": decodeRuleObject(t, `{"entries":{"entry":{"run_id":"one"}}}`), "b": decodeRuleObject(t, `{"entries":{"entry":{"run_id":"two"}}}`)}},
		{"run-id", map[string]any{"a": decodeRuleObject(t, `{"entries":{"one":{"run_id":"run"}}}`), "b": decodeRuleObject(t, `{"entries":{"two":{"run_id":"run"}}}`)}},
	} {
		t.Run(test.name, func(t *testing.T) {
			history := replacementHistory{plans: test.plans, entries: map[string]any{}, entryPlans: map[string]any{}}
			if err := history.indexEntryIdentities(); err == nil {
				t.Fatal("ambiguous replacement identity admitted")
			}
		})
	}
	history := replacementHistory{owner: owner, plans: map[string]any{}, byVersion: map[[2]string]any{}, byRun: map[string][]any{}}
	if err := history.indexRuns([]any{decodeRuleObject(t, `{"run_id":"r","run_version":"1"}`)}); err == nil {
		t.Fatal("unlinked run used as history")
	}
	history.root = decodeRuleObject(t, `{"plan_id":"root","entries":{"entry":{"plan_entry_id":"entry"}}}`)
	if _, err := history.follow("entry", []any{decodeRuleObject(t, `{"replacement_origin":{"ordinal":2}}`)}); err == nil {
		t.Fatal("noncontiguous replacement ordinal admitted")
	}
	history.byRun = map[string][]any{"run": {decodeRuleObject(t, `{"run_id":"run","run_version":"unexpected"}`)}}
	if err := history.parentVersions(decodeRuleObject(t, `{"run_id":"run","run_version":"1"}`), decodeRuleObject(t, `{"run_id":"run","run_version":"1"}`)); err == nil {
		t.Fatal("unexpected parent version admitted")
	}
	history.root = decodeRuleObject(t, `{"entries":{}}`)
	history.byRun = map[string][]any{"run": {decodeRuleObject(t, `{"run_id":"run","run_status":"superseded"}`)}}
	if _, err := history.analysisRuns(); err == nil {
		t.Fatal("orphan superseded run admitted")
	}
}

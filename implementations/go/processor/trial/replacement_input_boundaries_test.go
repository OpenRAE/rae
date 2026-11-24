package trial

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestReplacementHistoryRefusesChangedCommittedCarriersWithoutPartialAllocation(t *testing.T) {
	var reference struct {
		Request referenceRequest            `json:"request"`
		Root    binding.AdmittedTrialPlanV1 `json:"root"`
		Entry   string                      `json:"root_entry_id"`
		Cases   []replacementReferenceCase  `json:"cases"`
	}
	readTrialBoundaryJSON(t, "testdata/replacement-reference.json.gz", &reference)
	for _, field := range []string{"parent-model", "receipt-model", "plan-model", "superseded-content", "parent-task", "missing-provenance", "malformed-parent", "malformed-receipt"} {
		t.Run(field, func(t *testing.T) {
			checkCommittedReplacementBoundary(t, compilerRequest(t, reference.Request), reference.Root, reference.Entry, reference.Cases[0], field)
		})
	}
}
func checkCommittedReplacementBoundary(t *testing.T, compilation Request, root binding.AdmittedTrialPlanV1, entry string, reference replacementReferenceCase, field string) {
	t.Helper()
	raw, err := encoded(reference.Expected)
	if err != nil {
		t.Fatal(err)
	}
	var wire replacementWire
	if decode(raw, &wire) != nil {
		t.Fatal("committed replacement fixture")
	}
	prior := wire.result()
	request := ReplacementRequest{Compilation: compilation, OriginalPlan: root, RootEntryID: entry, ParentRun: reference.Parent, CleanupReceipts: reference.Receipts, PreviousAllocations: []ReplacementResult{prior}}
	switch field {
	case "parent-model":
		*prior.ParentRun = binding.ExperimentRunV1{}
	case "receipt-model":
		prior.CleanupReceipts = []binding.TrialCleanupReceiptV1{{}}
	case "plan-model":
		*prior.Plan = binding.AdmittedTrialPlanV1{}
	case "superseded-content":
		*prior.SupersededRun = binding.ExperimentRunV1{}
	case "parent-task":
		mutateReplacementRunBoundary(t, prior.ParentRun, "task_ref", map[string]any{"ref_kind": "task", "ref_id": "foreign", "ref_version": "1"})
	case "missing-provenance":
		request.PreviousAllocations = nil
		mutateReplacementRunBoundary(t, &request.ParentRun, "trial_provenance", nil)
	case "malformed-parent":
		request.PreviousAllocations = nil
		corruptReplacementField(t, &request.ParentRun.Invalidation)
	case "malformed-receipt":
		request.PreviousAllocations = nil
		request.CleanupReceipts = []binding.TrialCleanupReceiptV1{{}}
		corruptReplacementField(t, &request.CleanupReceipts[0].CleanStateClaim)
	}
	if len(request.PreviousAllocations) > 0 {
		request.PreviousAllocations[0] = prior
	}
	result, compileErr := CompileReplacement(t.Context(), request)
	if compileErr != nil || result.Plan != nil || result.ParentRun != nil || result.SupersededRun != nil || len(result.Diagnostics) == 0 {
		t.Fatal("changed committed replacement did not fail atomically", compileErr, result.Diagnostics)
	}
}
func mutateReplacementRunBoundary(t *testing.T, run *binding.ExperimentRunV1, field string, value any) {
	t.Helper()
	raw, err := encoded(run)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if decode(raw, &document) != nil {
		t.Fatal("run fixture")
	}
	document[field] = value
	raw, err = encoded(document)
	if err != nil {
		t.Fatal(err)
	}
	if decode(raw, run) != nil {
		t.Fatal("changed run fixture")
	}
}
func corruptReplacementField(t *testing.T, field *binding.Field[json.RawMessage]) {
	t.Helper()
	if err := field.UnmarshalJSON([]byte(`{}`)); err != nil {
		t.Fatal(err)
	}
	raw, ok := field.Value()
	if !ok {
		t.Fatal("raw field missing")
	}
	raw[0] = '['
}

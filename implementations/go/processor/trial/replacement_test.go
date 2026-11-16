package trial

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type replacementWire struct {
	Plan        *binding.AdmittedTrialPlanV1    `json:"plan"`
	Superseded  *binding.ExperimentRunV1        `json:"superseded_run"`
	Parent      *binding.ExperimentRunV1        `json:"parent_run"`
	Receipts    []binding.TrialCleanupReceiptV1 `json:"cleanup_receipts"`
	Diagnostics []referenceDiagnostic           `json:"diagnostics"`
}

func (w replacementWire) result() ReplacementResult {
	diagnostics := make([]diagnostic.Diagnostic, len(w.Diagnostics))
	for index, d := range w.Diagnostics {
		diagnostics[index] = d.native()
	}
	return ReplacementResult{Plan: w.Plan, SupersededRun: w.Superseded, ParentRun: w.Parent, CleanupReceipts: w.Receipts, Diagnostics: diagnostics}
}
func TestReplacementMatchesIndependentDecisionsAndRefusals(t *testing.T) {
	raw, err := readCompressedReference("testdata/replacement-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var ref struct {
		Request referenceRequest            `json:"request"`
		Root    binding.AdmittedTrialPlanV1 `json:"root"`
		Entry   string                      `json:"root_entry_id"`
		Cases   []replacementReferenceCase  `json:"cases"`
	}
	if json.Unmarshal(raw, &ref) != nil {
		t.Fatal("invalid replacement reference")
	}
	if len(ref.Cases) != 11 {
		t.Fatal("replacement case inventory changed")
	}
	request := compilerRequest(t, ref.Request)
	for _, test := range ref.Cases {
		t.Run(test.Name, func(t *testing.T) { checkReplacementReference(t, test, request, ref.Root, ref.Entry) })
	}
}

func replacementReference(result ReplacementResult) replacementWire {
	diagnostics := make([]referenceDiagnostic, len(result.Diagnostics))
	for index, d := range result.Diagnostics {
		diagnostics[index] = referenceDiagnosticOf(d)
	}
	return replacementWire{result.Plan, result.SupersededRun, result.ParentRun, result.CleanupReceipts, diagnostics}
}

type replacementReferenceCase struct {
	Name     string                          `json:"name"`
	Parent   binding.ExperimentRunV1         `json:"parent_run"`
	Receipts []binding.TrialCleanupReceiptV1 `json:"cleanup_receipts"`
	History  []replacementWire               `json:"history"`
	Expected replacementWire                 `json:"expected"`
}

func checkReplacementReference(t *testing.T, test replacementReferenceCase, request Request, root binding.AdmittedTrialPlanV1, entry string) {
	t.Helper()

	history := make([]ReplacementResult, len(test.History))
	for i, v := range test.History {
		history[i] = v.result()
	}
	result, err := CompileReplacement(context.Background(), ReplacementRequest{Compilation: request, OriginalPlan: root, RootEntryID: entry, ParentRun: test.Parent, CleanupReceipts: test.Receipts, PreviousAllocations: history})
	if err != nil {
		t.Fatal(err)
	}
	if (result.Plan == nil) != (test.Expected.Plan == nil) {
		t.Fatal("decision presence mismatch", result.Diagnostics)
	}
	actual := replacementReference(result)
	a, e1 := canonical(actual)
	b, e2 := canonical(test.Expected)
	if e1 != nil || e2 != nil {
		t.Fatal("result encoding failed")
	}
	if !sameJSON(a, b) {
		var left, right any
		_ = json.Unmarshal(a, &left)
		_ = json.Unmarshal(b, &right)
		t.Fatal(cmp.Diff(right, left))
	}
}

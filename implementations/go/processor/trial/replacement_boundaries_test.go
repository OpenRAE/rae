package trial

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func TestReplacementRefusesUncommittedHistoryAndUnboundedTraversal(t *testing.T) {
	var reference struct {
		Request referenceRequest
		Root    binding.AdmittedTrialPlanV1
		Entry   string `json:"root_entry_id"`
		Cases   []replacementReferenceCase
	}
	readTrialBoundaryJSON(t, "testdata/replacement-reference.json.gz", &reference)
	request := compilerRequest(t, reference.Request)
	first := reference.Cases[0].Expected.result()
	for _, test := range []string{"missing-plan", "missing-parent", "missing-supersession", "failed-decision", "history-bytes", "cancelled"} {
		t.Run(test, func(t *testing.T) {
			checkUncommittedReplacementBoundary(t, first, request, test)
		})
	}
	for _, test := range []string{"root", "entry", "history", "work"} {
		t.Run("root-"+test, func(t *testing.T) {
			input := ReplacementRequest{Compilation: request, OriginalPlan: reference.Root, RootEntryID: reference.Entry}
			switch test {
			case "root":
				input.OriginalPlan = binding.AdmittedTrialPlanV1{}
			case "entry":
				input.RootEntryID = "foreign"
			case "history":
				input.PreviousAllocations = []ReplacementResult{first, first, first}
			case "work":
				input.Compilation.Limits.MaxCoordinates = 1
			}
			result, err := CompileReplacement(t.Context(), input)
			if err != nil || result.Plan != nil || len(result.Diagnostics) != 1 {
				t.Fatal("invalid replacement root did not fail atomically", err, result.Diagnostics)
			}
		})
	}
}

func TestReplacementReceiptSetMustResolveEveryAttemptExactlyOnce(t *testing.T) {
	run := replacementArchive{entry: "entry", terminal: "attempt", attempts: []attemptReference{{ID: "attempt", Receipt: "receipt"}}}
	valid := replacementReceipt{id: "receipt", attempt: "attempt", entry: "entry", raw: json.RawMessage(`{}`)}
	for _, test := range []struct {
		name     string
		receipts []replacementReceipt
		valid    bool
	}{
		{"exact", []replacementReceipt{valid}, true}, {"missing", nil, false}, {"duplicate", []replacementReceipt{valid, valid}, false},
		{"foreign-entry", []replacementReceipt{{id: "receipt", attempt: "attempt", entry: "foreign"}}, false},
		{"foreign-receipt", []replacementReceipt{{id: "foreign", attempt: "attempt", entry: "entry"}}, false},
		{"foreign-attempt", []replacementReceipt{{id: "receipt", attempt: "foreign", entry: "entry"}}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			_, _, err := replacementReceiptSet(run, test.receipts)
			if (err == nil) != test.valid {
				t.Fatal("replacement receipt authority", err)
			}
		})
	}
	if sameReplacementReceipts([]replacementReceipt{valid}, nil) {
		t.Fatal("missing receipt replay admitted")
	}
	changed := valid
	changed.raw = json.RawMessage(`{"changed":true}`)
	if sameReplacementReceipts([]replacementReceipt{valid}, []replacementReceipt{changed}) {
		t.Fatal("changed receipt replay admitted")
	}
	for _, test := range []struct {
		name           string
		index, ordinal int
		replicate      string
	}{
		{"negative-index", -1, 1, "replicate-000001"}, {"missing-index", 1, 1, "replicate-000001"},
		{"malformed-coordinate", 0, 1, "foreign"}, {"overflow", 0, 1000000, "replicate-000001"},
	} {
		t.Run(test.name, func(t *testing.T) {
			value := test.replicate
			_, err := (replacementContext{index: test.index, maximum: 2, origin: replacementOrigin{Ordinal: test.ordinal}}).coordinates([]coordinate{{ReplicateID: &value}})
			if err == nil {
				t.Fatal("invalid replacement coordinate admitted")
			}
		})
	}
}

func checkUncommittedReplacementBoundary(t *testing.T, first ReplacementResult, request Request, test string) {
	t.Helper()

	prior := first
	compilation := request
	ctx := t.Context()
	switch test {
	case "missing-plan":
		prior.Plan = nil
	case "missing-parent":
		prior.ParentRun = nil
	case "missing-supersession":
		prior.SupersededRun = nil
	case "failed-decision":
		prior.Diagnostics = []diagnostic.Diagnostic{{Code: "refused"}}
	case "history-bytes":
		compilation.Limits.MaxPlanBytes = 1
	case "cancelled":
		cancelled, cancel := context.WithCancel(ctx)
		cancel()
		ctx = cancelled
	}
	state := replacementHistoryState{}
	err := state.observe(ctx, ReplacementRequest{Compilation: compilation}, trialPlan{}, replacementPolicy{}, prior, 0, replacementArchive{}, nil)
	if err == nil {
		t.Fatal("uncommitted or unbounded history admitted")
	}
	if test == "cancelled" && !errors.Is(err, context.Canceled) {
		t.Fatal("history lost cancellation", err)
	}
}

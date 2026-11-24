package experiment

import (
	"context"
	"encoding/json"
	"errors"
	"maps"
	"os"
	"slices"
	"sync"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/trial"
)

type testJournal struct {
	mu      sync.Mutex
	records []Decision
}

func (j *testJournal) Load(context.Context) ([]Decision, error) {
	j.mu.Lock()
	defer j.mu.Unlock()
	return append([]Decision(nil), j.records...), nil
}
func (j *testJournal) Claim(_ context.Context, d Decision) (bool, error) {
	j.mu.Lock()
	defer j.mu.Unlock()
	for _, prior := range j.records {
		if prior.ID() == d.ID() {
			if !same(decisionMap(prior), decisionMap(d)) {
				return false, fault.New(fault.Conflict, "journal-conflict", nil)
			}
			return false, nil
		}
	}
	j.records = append(j.records, d)
	return true, nil
}

type testCalls struct{}

func (testCalls) Call(ctx context.Context, _ string, _ time.Duration, work func(context.Context) (any, error)) (any, error) {
	return work(ctx)
}

type testHost struct {
	events []string
	ceased bool
	fail   bool
}

func (h *testHost) Records(context.Context, Trial) (RecordSource, error) { return RecordSource{}, nil }
func (h *testHost) Authorize(context.Context, Identity, string) error    { return nil }
func (h *testHost) Admit(context.Context, Trial) (string, error) {
	h.events = append(h.events, "admit")
	return "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", nil
}
func (h *testHost) Configure(_ context.Context, t Trial) (Phase, error) {
	h.events = append(h.events, "configure")
	return Phase{State: termSucceeded, Observation: &Observation{Kind: termConfiguration, Configurations: t.Realization.ParticipantConfigurations}}, nil
}
func (h *testHost) Advance(context.Context, Trial) (Phase, error) {
	h.events = append(h.events, "advance")
	if h.fail {
		return Phase{}, errors.New("secret-owner-message")
	}
	return Phase{State: termSucceeded}, nil
}
func (h *testHost) Observe(context.Context, Trial) (Observation, error) {
	h.events = append(h.events, "observe")
	state := termRunning
	if h.ceased {
		state = termSucceeded
	}
	return Observation{Kind: termExecution, State: state, Ceased: h.ceased}, nil
}
func (h *testHost) Capture(context.Context, Trial) (Phase, error) {
	h.events = append(h.events, termCapture)
	return Phase{State: termSucceeded, Observation: &Observation{Kind: termCapture, Complete: true}}, nil
}
func (h *testHost) Cleanup(context.Context, Trial, string) (Phase, error) {
	h.events = append(h.events, termCleanup)
	return Phase{}, errors.New("cleanup-unavailable")
}
func (h *testHost) Stop(context.Context, Trial, string) (Phase, error) {
	h.events = append(h.events, "stop")
	return Phase{State: termSucceeded}, nil
}
func (h *testHost) PrepareRetry(context.Context, Trial) (Phase, error) {
	return Phase{}, errors.New("unused")
}
func (h *testHost) Verify(context.Context, Trial, Observation) error { return nil }

//nolint:ireturn // The public constructor returns the sealed coordinator interface.
func newRuntime(t *testing.T, h Host, j *testJournal) Coordinator {
	t.Helper()
	return newRuntimeWithInputs(t, h, j, runtimeInputs(t))
}

//nolint:ireturn // Exercise the public sealed coordinator interface.
func newRuntimeWithInputs(t *testing.T, h Host, j *testJournal, input trial.RealizationInputs) Coordinator {
	t.Helper()
	runtime, err := New(context.Background(), Options{Inputs: input, Identity: Identity{ActorID: "actor", AuthorizationScope: []string{termRun}}, Host: h, Journal: j, Calls: testCalls{}, Clock: func() time.Time { return time.Date(2026, 11, 15, 10, 0, 0, 0, time.UTC) }, AdmissionBudget: time.Second, ExecutionBudget: time.Second, StoreBudget: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	return runtime
}
func TestRuntimeRequiresOwnersAndPreservesActor(t *testing.T) {
	if _, err := New(context.Background(), Options{}); err == nil {
		t.Fatal("missing owners admitted")
	}
	h := &testHost{}
	j := &testJournal{}
	runtime := newRuntime(t, h, j)
	before := len(h.events)
	if _, err := runtime.Advance(context.Background(), Identity{ActorID: "other", AuthorizationScope: []string{termRun}}); err == nil {
		t.Fatal("wrong actor authorized")
	}
	if len(h.events) != before {
		t.Fatal("unauthorized effect")
	}
}
func TestRuntimeRetainsStartAndWaitsForCessation(t *testing.T) {
	h := &testHost{}
	j := &testJournal{}
	runtime := newRuntime(t, h, j)
	identity := Identity{ActorID: "actor", AuthorizationScope: []string{termRun}}
	for range 3 {
		if _, err := runtime.Advance(context.Background(), identity); err != nil {
			t.Fatal(err)
		}
	}
	if len(j.records) < 3 {
		t.Fatal("start or configuration lost")
	}
	for _, event := range h.events {
		if event == termCapture || event == termCleanup {
			t.Fatal("teardown before cessation")
		}
	}
	bundle, err := runtime.Records(context.Background(), identity, RecordOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if bundle.Accounting.StartedRuns != 1 || bundle.Accounting.UnresolvedRuns != 1 || bundle.Accounting.Attempts != 1 {
		t.Fatalf("lost partial accounting: %+v", bundle.Accounting)
	}
	if len(bundle.Runs) != 1 {
		t.Fatal("partial run missing")
	}
	if err = runtime.Cancel(context.Background(), identity); err != nil {
		t.Fatal(err)
	}
	if _, err = runtime.Advance(context.Background(), identity); err != nil {
		t.Fatal(err)
	}
	if h.events[len(h.events)-1] != "observe" {
		t.Fatal("stop acknowledgement treated as cessation")
	}
}

type terminalHost struct {
	*testHost

	evidence map[string]any
}

func (h terminalHost) Cleanup(_ context.Context, t Trial, reason string) (Phase, error) {
	h.events = append(h.events, termCleanup)
	view, err := transportView(t.Plan)
	if err != nil {
		return Phase{}, err
	}
	cleanup := at(view, "cleanup_plans", text(view, "entries", t.PlanEntryID, "execution_controls", "cleanup_plan_ref"))
	results := map[string]any{}
	evidence := []binding.ExperimentEvidenceRecordV1{}
	refs := []string{"evidence:clean"}
	for key, o := range object(at(cleanup, "cleanup_obligations")) {
		status := "not-triggered"
		requiredRefs := []string{}
		if slices.Contains(array(at(o, "triggers")), any(map[string]string{termSucceeded: "success", termFailed: "failure", termCancelled: termCancellation, termTimedOut: "timeout", termAborted: "abort"}[reason])) {
			status = termSucceeded
			requiredRefs = []string{"evidence:" + key}
			refs = append(refs, requiredRefs...)
		}
		results[key] = map[string]any{"obligation_id": key, "status": status, "evidence_refs": requiredRefs, "residual_state_refs": []string{}}
	}
	for _, id := range refs {
		raw, marshalErr := json.Marshal(h.evidence)
		if marshalErr != nil {
			return Phase{}, marshalErr
		}
		var item map[string]any
		if json.Unmarshal(raw, &item) != nil {
			return Phase{}, errors.New("fixture")
		}
		item["evidence_record_id"] = id
		object(item["run_ref"])[termRefID] = t.RunID
		var record binding.ExperimentEvidenceRecordV1
		if convert(item, &record) != nil {
			return Phase{}, errors.New("fixture")
		}
		evidence = append(evidence, record)
	}
	receipt := map[string]any{"schema_version": "trial-cleanup-receipt/v1", "receipt_id": "cleanup:" + t.ExecutionAttemptID, "cleanup_plan_ref": at(cleanup, termPlanID), termPlanEntryID: t.PlanEntryID, termRunID: t.RunID, termExecutionAttemptID: t.ExecutionAttemptID, "trial_outcome": reason, "cleanup_status": termSucceeded, "obligation_results": results, "clean_state_claim": map[string]any{"disposition": "verified-clean", "boundary_refs": slices.Sorted(maps.Keys(object(at(cleanup, "resource_boundaries")))), "evidence_refs": []string{"evidence:clean"}}}
	var dto binding.TrialCleanupReceiptV1
	if convert(receipt, &dto) != nil {
		return Phase{}, errors.New("fixture")
	}
	return Phase{State: termSucceeded, Observation: &Observation{Kind: termCleanup, CleanupReceipt: &dto, Evidence: evidence}}, nil
}
func fixtureEvidence(t *testing.T) map[string]any {
	t.Helper()
	raw, err := os.ReadFile("testdata/records-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture map[string]any
	if json.Unmarshal(raw, &fixture) != nil {
		t.Fatal("fixture")
	}
	for _, item := range array(fixture["cases"]) {
		for _, o := range array(at(item, "observations")) {
			if text(o, "observation", "kind") == termCapture {
				return object(array(at(o, "observation", termEvidence))[0])
			}
		}
	}
	t.Fatal("evidence missing")
	return nil
}
func TestRuntimeCompletesAllEntriesAndRetainsCleanup(t *testing.T) {
	h := terminalHost{testHost: &testHost{ceased: true}, evidence: fixtureEvidence(t)}
	j := &testJournal{}
	runtime := runtimeCoordinator(t, newRuntime(t, h, j))
	id := runtime.options.Identity
	complete := false
	for range 30 {
		progress, err := runtime.Advance(context.Background(), id)
		if err != nil {
			t.Fatal(err)
		}
		if progress.State == termCompleted {
			complete = true
			break
		}
		if progress.State == termCleanupFailed {
			t.Fatal("valid cleanup refused")
		}
	}
	if !complete {
		t.Fatal("did not complete")
	}
	results, err := runtime.Results(context.Background(), id)
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != len(runtime.slots) {
		t.Fatal("terminal results lost")
	}
	bundle, err := runtime.Records(context.Background(), id, RecordOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if bundle.Accounting.ResolvedRuns != 2 || bundle.Accounting.Attempts != 2 || len(bundle.EligibleRunIDs) != 0 {
		t.Fatalf("execution confused with science: %+v", bundle.Accounting)
	}
}
func TestRuntimeAttemptIdentityMatchesReference(t *testing.T) {
	reference := recordReferences(t)
	var first struct {
		ExecutionAttemptID string `json:"execution_attempt_id"`
	}
	if json.Unmarshal(reference.Cases[0].Attempts[0], &first) != nil {
		t.Fatal("bad attempt")
	}
	input := runtimeInputs(t)
	view, _ := transportView(input.Plan)
	schedule, err := trial.PlanBatchSchedule(input.Plan)
	if err != nil || schedule.Entries[0].PlanEntryID != reference.EntryID {
		t.Fatal("reference entry is not first in dispatch order", err)
	}
	got := attemptID(text(view, termPlanID), reference.EntryID, 1)
	if got != first.ExecutionAttemptID {
		t.Fatal(got, first.ExecutionAttemptID)
	}
}

func runtimeCoordinator(t *testing.T, runtime Coordinator) *coordinator {
	t.Helper()
	c, ok := runtime.(*coordinator)
	if !ok {
		t.Fatal("native coordinator missing")
	}
	return c
}

func (h *testHost) Cancel(context.Context, Trial) error {
	h.events = append(h.events, "cancel")
	return nil
}
func (h terminalHost) Observe(ctx context.Context, trial Trial) (Observation, error) {
	observed, err := h.testHost.Observe(ctx, trial)
	if err != nil {
		return observed, err
	}
	if observed.Ceased {
		record, proofErr := trialEvidence(h.evidence, trial.RunID, "evidence:execution")
		if proofErr != nil {
			return observed, proofErr
		}
		observed.Evidence = []binding.ExperimentEvidenceRecordV1{record}
	}
	return observed, nil
}
func trialEvidence(template map[string]any, runID, id string) (binding.ExperimentEvidenceRecordV1, error) {
	var result binding.ExperimentEvidenceRecordV1
	view, err := transportView(template)
	if err != nil {
		return result, err
	}
	view["evidence_record_id"] = id
	reference := object(view["run_ref"])
	if reference == nil {
		return result, errors.New("fixture run reference missing")
	}
	reference[termRefID] = runID
	err = convert(view, &result)
	return result, err
}

func (h *testHost) Retire(context.Context, Trial) error            { return nil }
func (h *testHost) IsRetired(context.Context, Trial) (bool, error) { return false, nil }

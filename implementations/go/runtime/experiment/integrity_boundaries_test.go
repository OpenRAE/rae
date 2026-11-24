package experiment

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestStudyReplacementHistoryRetainsVersionsAndScopedCleanup(t *testing.T) {
	f := prepareReplacementRuntime(t, false)
	if _, err := f.c.Advance(t.Context(), f.options.Identity); err != nil {
		t.Fatal(err)
	}
	var parent trialSlot
	for _, slot := range f.c.slotSnapshot() {
		if slot.entry.PlanEntryID == f.ref.EntryID {
			parent = slot
		}
	}
	source := recordSourceForSlot(t, parent, f.ref.Case)
	state := studyValidation{coordinator: f.c, bundle: RecordBundle{Sources: []RecordSource{source}}, versions: map[string]any{}}
	if err := state.prepare(); err != nil {
		t.Fatal(err)
	}
	if err := state.replacementHistory(f.journal.records); err != nil {
		t.Fatal(err)
	}
	if len(state.inputs.ReplacementPlans) != 1 || len(state.inputs.Runs) != 2 || len(state.inputs.CleanupReceipts) == 0 {
		t.Fatal("study lost a replacement plan, retained run version, or cleanup receipt")
	}
	before := len(state.inputs.Runs)
	if err := state.addRun(object(state.versions[versionKey(termRun, decisionMap(onlyReplacementDecision(t, f.journal.records))["parent_run"])])); err != nil || len(state.inputs.Runs) != before {
		t.Fatal("identical retained version was not idempotent", err)
	}
	foreign := object(decisionMap(onlyReplacementDecision(t, f.journal.records))["parent_run"])
	foreign["run_version"] = "unresolved-version"
	state.bundle.Sources = nil
	if err := state.addRun(foreign); err == nil {
		t.Fatal("run without a matching record source admitted")
	}
}

func TestStudyCleanupPlanRequiresOneConsistentRetainedIdentity(t *testing.T) {
	plan := map[string]any{"cleanup_plans": map[string]any{"clean": map[string]any{"plan_id": "clean", "run_id": "run"}}}
	other := map[string]any{"cleanup_plans": map[string]any{"clean": map[string]any{"plan_id": "clean", "run_id": "foreign"}}}
	for _, test := range []struct {
		name  string
		plans []any
		id    string
		valid bool
	}{
		{"exact", []any{plan}, "clean", true}, {"identical-replay", []any{plan, plan}, "clean", true},
		{"missing", []any{plan}, "foreign", false}, {"conflicting-version", []any{plan, other}, "clean", false},
		{"no-plans", nil, "clean", false},
	} {
		t.Run(test.name, func(t *testing.T) {
			if _, err := studyCleanupPlan(test.plans, test.id); (err == nil) != test.valid {
				t.Fatalf("cleanup authority = %v, want %v", err, test.valid)
			}
		})
	}
}

type boundaryJournal struct {
	records []Decision
	err     error
	claimed bool
}

func (j *boundaryJournal) Load(context.Context) ([]Decision, error) { return j.records, j.err }
func (j *boundaryJournal) Claim(context.Context, Decision) (bool, error) {
	return j.claimed, j.err
}

func TestRuntimeJournalReplaysExactDecisionsAndRefusesMissingClaims(t *testing.T) {
	base := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	m := map[string]any{termExperimentID: base.id, termPlanDigest: base.schedule.PlanDigest, "realization_digests": []string{base.slots[0].commitment}, "actor_id": base.options.Identity.ActorID, "authorization_scope": base.options.Identity.AuthorizationScope}
	decision, err := makeDecision(experimentSchema, m)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name    string
		records []Decision
		valid   bool
	}{
		{"identical", []Decision{decision}, true}, {"duplicate-identical", []Decision{decision, decision}, true},
		{"missing", nil, false}, {"nil-record", []Decision{nil}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			base.options.Journal = &boundaryJournal{records: test.records}
			actual, claimErr := base.claim(t.Context(), experimentSchema, m)
			if (claimErr == nil) != test.valid {
				t.Fatalf("journal reconciliation = %v, want %v", claimErr, test.valid)
			}
			if test.valid && actual.ID() != decision.ID() {
				t.Fatal("replay changed immutable identity")
			}
		})
	}
	base.options.Journal = &boundaryJournal{err: errors.New("private journal detail")}
	if _, err = base.load(t.Context()); err == nil || strings.Contains(err.Error(), "private") {
		t.Fatal("journal failure was lost or disclosed", err)
	}
	if _, err = base.claim(t.Context(), experimentSchema, m); err == nil || strings.Contains(err.Error(), "private") {
		t.Fatal("claim failure was lost or disclosed", err)
	}
}

type boundaryCalls struct{ result any }

func (c boundaryCalls) Call(context.Context, string, time.Duration, func(context.Context) (any, error)) (any, error) {
	return c.result, nil
}

func TestRuntimeOwnerAdapterRejectsWrongResultsAndExpiredCalls(t *testing.T) {
	c := &coordinator{options: Options{Calls: boundaryCalls{result: "foreign-result"}}}
	if _, err := ownerCall(t.Context(), c, "store", time.Second, func(context.Context) (bool, error) { return true, nil }); err == nil {
		t.Fatal("wrong owner result type admitted")
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if _, err := ownerCall(ctx, c, "store", time.Second, func(context.Context) (bool, error) { t.Fatal("cancelled work dispatched"); return true, nil }); !errors.Is(err, context.Canceled) {
		t.Fatal("cancelled owner call lost cancellation", err)
	}
	c.options.Calls = testCalls{}
	for _, source := range []error{fault.New(fault.Conflict, "owner-conflict", nil), fault.New(fault.Category(255), "private-definition", nil), errors.New("private owner detail")} {
		_, err := ownerCall(t.Context(), c, "store", time.Second, func(context.Context) (bool, error) { return false, source })
		if err == nil || strings.Contains(err.Error(), "private") {
			t.Fatal("owner error category was lost or foreign detail escaped", err)
		}
	}
	c.options.AdmissionBudget = time.Millisecond
	c.gate = make(chan struct{}, 1)
	c.gate <- struct{}{}
	if _, err := c.acquire(t.Context()); err == nil {
		t.Fatal("busy progress ignored admission budget")
	}
	if _, err := c.acquire(ctx); !errors.Is(err, context.Canceled) {
		t.Fatal("busy progress lost cancellation", err)
	}
}

func TestRuntimeEveryPublicOperationChecksActorAndScope(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	for _, id := range []Identity{{ActorID: "foreign", AuthorizationScope: c.options.Identity.AuthorizationScope}, {ActorID: c.options.Identity.ActorID, AuthorizationScope: []string{"foreign"}}} {
		for _, operation := range []string{"advance", "cancel", "results", "records"} {
			t.Run(id.ActorID+"/"+id.AuthorizationScope[0]+"/"+operation, func(t *testing.T) {
				var err error
				switch operation {
				case "advance":
					_, err = c.Advance(t.Context(), id)
				case "cancel":
					err = c.Cancel(t.Context(), id)
				case "results":
					_, err = c.Results(t.Context(), id)
				case "records":
					_, err = c.Records(t.Context(), id, RecordOptions{})
				}
				category, known := fault.CategoryOf(err)
				if !known || category != fault.Authorization {
					t.Fatal("foreign actor or scope admitted", err)
				}
			})
		}
	}
	if _, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Metadata: map[string]RunMetadata{"unstarted": {}}}); err == nil {
		t.Fatal("metadata for an unstarted run admitted")
	}
	if err := c.publishRecords(t.Context(), RecordBundle{Runs: []binding.ExperimentRunV1{{}}}, &testArchive{}, nil); err == nil {
		t.Fatal("publication admitted missing validation records")
	}
}

type replacementSequenceReference struct {
	ChildCase        recordReferenceCase `json:"child_case"`
	SecondChild      json.RawMessage     `json:"second_child"`
	SecondSuperseded json.RawMessage     `json:"second_superseded_run"`
}

func prepareReplacementSequenceBoundary(t *testing.T) (replacementRuntimeFixture, replacementSequenceReference, trialSlot) {
	t.Helper()
	raw, err := os.ReadFile("testdata/replacement-sequence-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference replacementSequenceReference
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("replacement sequence fixture")
	}
	f := prepareReplacementRuntime(t, false)
	if _, err = f.c.Advance(t.Context(), f.options.Identity); err != nil {
		t.Fatal(err)
	}
	if err = f.c.restoreChildren(t.Context(), f.journal.records); err != nil {
		t.Fatal(err)
	}
	var child trialSlot
	for _, slot := range f.c.slotSnapshot() {
		if slot.root == f.ref.EntryID && slot.entry.PlanEntryID != f.ref.EntryID {
			child = slot
		}
	}
	if child.entry.PlanEntryID == "" {
		t.Fatal("first child was not restored")
	}
	return f, reference, child
}
func TestRuntimeSecondReplacementReplaysTheCompleteOrderedPrefix(t *testing.T) {
	f, reference, child := prepareReplacementSequenceBoundary(t)
	source := recordSourceForSlot(t, child, reference.ChildCase)
	f.journal.records = append(f.journal.records, source.Attempts...)
	f.journal.records = append(f.journal.records, source.Observations...)
	trial := child.request(decisionMap(source.Attempts[0]))
	trial.Identity = f.options.Identity
	if err := f.c.recordTerminal(t.Context(), child, trial, attemptObservations(source.Observations, trial.ExecutionAttemptID), termSucceeded); err != nil {
		t.Fatal(err)
	}
	if convert(reference.ChildCase.Run, &f.archive.run) != nil {
		t.Fatal("child archive fixture")
	}
	if _, err := f.c.Advance(t.Context(), f.options.Identity); err != nil {
		t.Fatal("second replacement", err)
	}
	replacements := []Decision{}
	for _, record := range f.journal.records {
		if record.SchemaVersion() == replacementSchema {
			replacements = append(replacements, record)
		}
	}
	if len(replacements) != 2 || f.archive.builds != 2 || f.host.retireCalls != 2 {
		t.Fatal("replacement prefix repeated or lost work", len(replacements), f.archive.builds, f.host.retireCalls)
	}
	assertScienceJSON(t, decisionMap(replacements[1])["plan"], reference.SecondChild)
	assertScienceJSON(t, decisionMap(replacements[1])["superseded_run"], reference.SecondSuperseded)
	checkReplacementPrefixRecovery(t, f)
}
func checkReplacementPrefixRecovery(t *testing.T, f replacementRuntimeFixture) {
	t.Helper()
	recovered, newErr := New(t.Context(), f.options)
	if newErr != nil {
		t.Fatal(newErr)
	}
	c := runtimeCoordinator(t, recovered)
	if err := c.restoreChildren(t.Context(), f.journal.records); err != nil {
		t.Fatal(err)
	}
	if err := c.restoreChildren(t.Context(), f.journal.records); err != nil || len(c.slotSnapshot()) != 4 {
		t.Fatal("replacement recovery was not idempotent", err)
	}
	var latest trialSlot
	for _, slot := range c.slotSnapshot() {
		view, _ := transportView(slot.plan)
		if integer(at(view, "replacement_origin", "ordinal")) == 2 {
			latest = slot
		}
	}
	history, replayed, historyErr := c.replacementHistory(t.Context(), latest, Trial{RunID: latest.entry.RunID}, f.journal.records, f.archive)
	if historyErr != nil || replayed || len(history) != 2 {
		t.Fatal("complete replacement prefix was not reconstructed", historyErr)
	}
	for index, result := range history {
		view, _ := transportView(result.Plan)
		if integer(at(view, "replacement_origin", "ordinal")) != index+1 {
			t.Fatal("replacement prefix order changed")
		}
	}
}

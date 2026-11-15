package experiment

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/trial"
)

type replacementRuntimeReference struct {
	runtimeReferenceCompilation

	EntryID       string              `json:"entry_id"`
	Case          recordReferenceCase `json:"case"`
	Child         json.RawMessage     `json:"child"`
	SupersededRun json.RawMessage     `json:"superseded_run"`
}
type replacementArchiveOwner struct {
	*testArchive

	run    binding.ExperimentRunV1
	builds int
}

func (a *replacementArchiveOwner) BuildRun(context.Context, RecordSource) (binding.ExperimentRunV1, error) {
	a.builds++
	return a.run, nil
}
func replacementCompilationFixture(t *testing.T, input trial.RealizationInputs, ref runtimeReferenceRequest) trial.Request {
	t.Helper()
	owner, err := experimentOwner()
	if err != nil {
		t.Fatal(err)
	}
	request := trial.Request{Family: input.Family, Task: input.Task, Experiment: input.Experiment, RealizationEnvelope: input.RealizationEnvelope, ApparatusManifests: input.ApparatusManifests, CaptureSpecs: input.CaptureSpecs, Limits: trial.DefaultLimits(), MixedCompositionLimits: trial.DefaultMixedCompositionLimits()}
	for _, item := range []struct {
		raw     json.RawMessage
		profile admission.FragmentProfile
		target  *admission.Fragment
	}{{ref.InputRefs, admission.TrialInputRefs, &request.InputRefs}, {ref.Apparatus, admission.TrialApparatus, &request.Apparatus}, {ref.ExecutionAuthority, admission.TrialExecutionAuthority, &request.ExecutionAuthority}} {
		parsed, parseErr := ingress.Parse(item.raw, runtimeIngress(), ingress.Object)
		if parseErr != nil {
			t.Fatal(parseErr)
		}
		*item.target, err = admission.AdmitFragment(owner, item.profile, parsed, runtimeIngress())
		if err != nil {
			t.Fatal(err)
		}
	}
	return request
}
func TestRuntimeReplacementRetainsChildBeforeRetirementAndRecoversArchive(t *testing.T) {
	for _, lost := range []bool{false, true} {
		t.Run(map[bool]string{false: "ordinary", true: "lost-archive-acknowledgement"}[lost], func(t *testing.T) { checkReplacementRecovery(t, lost) })
	}
}
func checkReplacementRecovery(t *testing.T, lost bool) {
	t.Helper()
	f := prepareReplacementRuntime(t, lost)
	c, options, archive, host, journal, ref, attempt := f.c, f.options, f.archive, f.host, f.journal, f.ref, f.attempt
	_, err := c.Advance(t.Context(), options.Identity)
	if lost {
		if err == nil {
			t.Fatal("lost archive acknowledgement accepted")
		}
		runtime, newErr := New(t.Context(), options)
		if newErr != nil {
			t.Fatal(newErr)
		}
		c = runtimeCoordinator(t, runtime)
		_, err = c.Advance(t.Context(), options.Identity)
	}
	if err != nil {
		t.Fatal(err)
	}
	if !host.retired[attempt.RunID] || host.retireCalls != 1 {
		t.Fatal("completed parent was not retired")
	}
	child := onlyReplacementDecision(t, journal.records)
	assertScienceJSON(t, decisionMap(child)["plan"], ref.Child)
	assertScienceJSON(t, decisionMap(child)["superseded_run"], ref.SupersededRun)
	if archive.builds != 1 {
		t.Fatalf("candidate reconstructed %d times", archive.builds)
	}
	runtime, newErr := New(t.Context(), options)
	if newErr != nil {
		t.Fatal(newErr)
	}
	c = runtimeCoordinator(t, runtime)
	_, err = c.Advance(t.Context(), options.Identity)
	if err != nil {
		t.Fatal(err)
	}
	if len(c.slotSnapshot()) != 3 || host.retireCalls != 1 || archive.builds != 1 {
		t.Fatal("recovery repeated parent work or lost child")
	}
}

type replacementRuntimeFixture struct {
	c       *coordinator
	options Options
	archive *replacementArchiveOwner
	host    *retirementHost
	journal *testJournal
	ref     replacementRuntimeReference
	attempt Trial
}

func prepareReplacementRuntime(t *testing.T, lost bool) replacementRuntimeFixture {
	t.Helper()
	raw, err := os.ReadFile("testdata/runtime-replacement-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var ref replacementRuntimeReference
	if json.Unmarshal(raw, &ref) != nil {
		t.Fatal("fixture")
	}
	input := runtimeInputFixture(t, ref.runtimeReferenceCompilation)
	compilation := replacementCompilationFixture(t, input, ref.Request)
	archive := &replacementArchiveOwner{testArchive: &testArchive{runs: map[string]binding.ExperimentRunV1{}, loseAck: lost}}
	if convert(ref.Case.Run, &archive.run) != nil {
		t.Fatal("run fixture")
	}
	host := &retirementHost{testHost: &testHost{}, evidence: fixtureEvidence(t), retired: map[string]bool{}}
	journal := &testJournal{}
	host.beforeRetire = func(trial Trial) error {
		for _, record := range journal.records {
			if record.SchemaVersion() == replacementSchema && text(decisionMap(record), "parent_run", "run_id") == trial.RunID {
				return nil
			}
		}
		return errors.New("parent retirement preceded durable child allocation")
	}

	options := Options{Inputs: input, Replacement: &compilation, Archive: archive, Host: host, Journal: journal, Calls: testCalls{}, Identity: Identity{ActorID: "actor", AuthorizationScope: []string{termRun}}, Clock: func() time.Time { return time.Date(2026, 11, 15, 10, 0, 1, 0, time.UTC) }, AdmissionBudget: time.Second, ExecutionBudget: time.Second, StoreBudget: time.Second}
	runtime, newErr := New(t.Context(), options)
	if newErr != nil {
		t.Fatal(newErr)
	}
	c := runtimeCoordinator(t, runtime)
	var parent trialSlot
	for _, slot := range c.slotSnapshot() {
		if slot.entry.PlanEntryID == ref.EntryID {
			parent = slot
		} else {
			host.retired[slot.entry.RunID] = true
		}
	}
	source := recordSourceForSlot(t, parent, ref.Case)
	journal.records = append(journal.records, source.Attempts...)
	journal.records = append(journal.records, source.Observations...)
	attempt := parent.request(decisionMap(source.Attempts[0]))
	attempt.Identity = options.Identity
	if err = c.recordTerminal(t.Context(), parent, attempt, attemptObservations(source.Observations, attempt.ExecutionAttemptID), termSucceeded); err != nil {
		t.Fatal(err)
	}
	return replacementRuntimeFixture{c, options, archive, host, journal, ref, attempt}
}

//nolint:ireturn // The fixture asserts the sealed journal decision from the public interface.
func onlyReplacementDecision(t *testing.T, records []Decision) Decision {
	t.Helper()
	var child Decision
	for _, record := range records {
		if record.SchemaVersion() == replacementSchema {
			if child != nil {
				t.Fatal("duplicate replacement decision")
			}
			child = record
		}
	}
	if child == nil {
		t.Fatal("retirement lost child decision")
	}

	return child
}

package experiment

import (
	"encoding/json"
	"maps"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestRestoredSlotsRemainIdempotentAndConflictsAreAtomic(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	original := c.slotSnapshot()
	if len(original) < 2 {
		t.Fatal("two-entry restoration fixture missing")
	}
	if err := c.appendSlots(original); err != nil || len(c.slotSnapshot()) != len(original) {
		t.Fatal("identical restored slots were duplicated", err)
	}
	c.slots = original[:1]
	conflicting := original[0]
	conflicting.view = maps.Clone(conflicting.view)
	conflicting.view[termPlanDigest] = "different"
	if err := c.appendSlots([]trialSlot{original[1], conflicting}); err == nil {
		t.Fatal("conflicting slot admitted")
	}
	if len(c.slotSnapshot()) != 1 {
		t.Fatal("failed restoration published a partial slot set")
	}
}
func TestRuntimeRefusesAttemptReservationsAboveItsCapacityBeforeHostAdmission(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	view, err := transportView(c.options.Inputs.Plan)
	if err != nil {
		t.Fatal(err)
	}
	for _, plan := range object(view["cleanup_plans"]) {
		object(at(plan, "retry_policy"))["max_attempts"] = json.Number("1001")
	}
	raw, err := json.Marshal(view)
	if err != nil {
		t.Fatal(err)
	}
	owner, err := experimentOwner()
	if err != nil {
		t.Fatal(err)
	}
	admitted, err := admission.SealTrialPlan(owner, raw, runtimeIngress())
	if err != nil {
		t.Fatal("bounded-plan fixture", err)
	}
	var plan binding.AdmittedTrialPlanV1
	if json.Unmarshal(admitted.JSON(), &plan) != nil {
		t.Fatal("sealed plan transport")
	}
	options := c.options
	options.Inputs.Plan = plan
	options.Journal = &testJournal{}
	host := &testHost{}
	options.Host = host
	_, err = New(t.Context(), options)
	category, known := fault.CategoryOf(err)
	if !known || category != fault.Conflict || len(host.events) != 0 {
		t.Fatal("attempt capacity reached installed admission", err, host.events)
	}
}
func TestRecordProductionKeepsStartedRunsWhenAStudyDefinitionIsInvalid(t *testing.T) {
	ref := scienceReference(t)
	c, _ := scienceRuntime(t, ref)
	for _, definition := range []binding.ExperimentStudyV1{{}, ref.Definition} {
		if !definition.StudyId.IsZero() {
			raw := []byte(`{"ref_kind":"study","ref_id":"definition","ref_version":"1","ref_digest":"sha256:` + strings.Repeat("a", 64) + `"}`)
			if err := definition.DefinitionRef.UnmarshalJSON(raw); err != nil {
				t.Fatal(err)
			}
		}
		bundle, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Study: &definition})
		if err == nil || len(bundle.Runs) != 1 || bundle.Study != nil {
			t.Fatal("invalid study hid started facts or became a snapshot", err)
		}
	}
}
func TestArchiveCandidateValidationRefusesPlanSourceAndVersionContradictions(t *testing.T) {
	f := prepareReplacementRuntime(t, false)
	var slot trialSlot
	for _, s := range f.c.slotSnapshot() {
		if s.entry.PlanEntryID == f.ref.EntryID {
			slot = s
		}
	}
	source := recordSourceForSlot(t, slot, f.ref.Case)
	runView, err := transportView(f.archive.run)
	if err != nil {
		t.Fatal(err)
	}
	altered := maps.Clone(runView)
	altered["deviations"] = []any{"Changed immutable content."}
	prior, err := makeDecision(candidateSchema, map[string]any{termExperimentID: f.c.id, termRun: altered})
	if err != nil {
		t.Fatal(err)
	}
	original, err := makeDecision(candidateSchema, map[string]any{termExperimentID: f.c.id, termRun: runView})
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name  string
		check func() error
	}{
		{"invalid-plan", func() error {
			bad := slot
			bad.plan = binding.AdmittedTrialPlanV1{}
			_, err := f.c.validateArchiveCandidate(bad, source, f.archive.run, nil)
			return err
		}},
		{"source-operations", func() error {
			bad := source
			bad.OperationRefs = map[string][]string{text(decisionMap(source.Attempts[0]), termExecutionAttemptID): {"foreign"}}
			_, err := f.c.validateArchiveCandidate(slot, bad, f.archive.run, nil)
			return err
		}},
		{"retained-version", func() error {
			_, err := f.c.validateArchiveCandidate(slot, source, f.archive.run, []Decision{prior})
			return err
		}},
		{"retained-conflict", func() error {
			_, err := f.c.validateArchiveCandidate(slot, source, f.archive.run, []Decision{prior, original})
			return err
		}},
		{"foreign-run", func() error {
			bad := f.archive.run
			if err := bad.RunId.UnmarshalJSON([]byte(`"foreign"`)); err != nil {
				return err
			}
			_, err := f.c.validateArchiveCandidate(slot, source, bad, nil)
			return err
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := test.check(); err == nil {
				t.Fatal("contradictory archive candidate admitted")
			}
		})
	}
}

package experiment

import (
	"encoding/json"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestArchiveCandidateMustMatchEveryRetainedAttemptAndCaptureFact(t *testing.T) {
	f := prepareReplacementRuntime(t, false)
	var slot trialSlot
	for _, s := range f.c.slotSnapshot() {
		if s.entry.PlanEntryID == f.ref.EntryID {
			slot = s
		}
	}
	source := recordSourceForSlot(t, slot, f.ref.Case)
	for _, field := range []string{"exact", "count", "attempt", "receipt", "operations", "operation-type", "capture"} {
		t.Run(field, func(t *testing.T) { checkArchiveSourceBoundary(t, source, f.archive.run, field) })
	}
	if _, err := f.c.validateArchiveCandidate(slot, source, binding.ExperimentRunV1{}, nil); err == nil {
		t.Fatal("unconstructed archive candidate admitted")
	}
}
func checkArchiveSourceBoundary(t *testing.T, source RecordSource, run binding.ExperimentRunV1, field string) {
	t.Helper()
	view, err := transportView(run)
	if err != nil {
		t.Fatal(err)
	}
	attempts := array(at(view, "trial_provenance", "execution_attempts"))
	if len(attempts) == 0 {
		t.Fatal("archive attempt fixture")
	}
	switch field {
	case "count":
		object(view["trial_provenance"])["execution_attempts"] = []any{}
	case "attempt":
		object(attempts[0])[termExecutionAttemptID] = "foreign"
	case "receipt":
		object(attempts[0])["cleanup_receipt_ref"] = "foreign"
	case "operations":
		object(attempts[0])[termOperationRefs] = []any{"foreign"}
	case "operation-type":
		object(attempts[0])[termOperationRefs] = []any{json.Number("1")}
	case "capture":
		view["run_status"] = termCompleted
		source.Observations = slices.DeleteFunc(slices.Clone(source.Observations), func(d Decision) bool { return text(decisionMap(d), "observation", "kind") == termCapture })
	}
	if got := archiveMatchesSource(view, source); got != (field == "exact") {
		t.Fatal("archive disagrees with retained source", field, got)
	}
}
func TestRecordReadersRejectConflictingContentAtAnImmutableVersion(t *testing.T) {
	ref := scienceReference(t)
	c, journal := scienceRuntime(t, ref)
	var view map[string]any
	if json.Unmarshal(ref.Case.Run, &view) != nil {
		t.Fatal("run fixture")
	}
	first, err := makeDecision(candidateSchema, map[string]any{termExperimentID: c.id, termRun: view})
	if err != nil {
		t.Fatal(err)
	}
	view["deviations"] = []any{"Different content at the same immutable version."}
	second, err := makeDecision(candidateSchema, map[string]any{termExperimentID: c.id, termRun: view})
	if err != nil {
		t.Fatal(err)
	}
	records := []Decision{first, second}
	for _, test := range []struct {
		name  string
		check func() error
	}{
		{"retained-versions", func() error { _, err := retainedVersions(records, c.id); return err }},
		{"scientific-originals", func() error { _, err := canonicalArchivalRuns(records, c.id); return err }},
		{"study-history", func() error { _, err := retainedStudyRuns(records, c.id); return err }},
		{"publication", func() error { return c.publishRecords(t.Context(), RecordBundle{}, &testArchive{}, records) }},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := test.check(); err == nil {
				t.Fatal("conflicting immutable content admitted")
			}
		})
	}
	journal.records = append(journal.records, records...)
	if _, err := c.Records(t.Context(), c.options.Identity, RecordOptions{}); err == nil {
		t.Fatal("record collection admitted a conflicting version")
	}
	state := studyValidation{versions: map[string]any{versionKey(termRun, view): map[string]any{"run_id": "different"}}}
	if err := state.addRun(view); err == nil {
		t.Fatal("study reused conflicting version")
	}
}
func TestPublicationRefusesMutatedCarriersBeforeFreezing(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	run := binding.ExperimentRunV1{}
	corruptBoundaryField(t, &run.Invalidation)
	for _, test := range []struct {
		name   string
		bundle RecordBundle
	}{
		{"history", RecordBundle{RetainedHistory: []binding.ExperimentRunV1{run}}},
		{"current", RecordBundle{Runs: []binding.ExperimentRunV1{run}, ValidationRecords: []binding.ExperimentRunV1{{}}}},
		{"validated", RecordBundle{Runs: []binding.ExperimentRunV1{{}}, ValidationRecords: []binding.ExperimentRunV1{run}}},
	} {
		t.Run(test.name, func(t *testing.T) {
			publication := recordPublication{coordinator: c, versions: map[string]any{}, byVersion: map[string]map[string]any{}}
			if err := publication.freeze(t.Context(), test.bundle); err == nil {
				t.Fatal("mutated run became frozen publication")
			}
		})
	}
	study := binding.ExperimentStudyV1{}
	corruptBoundaryField(t, &study.DefinitionRef)
	publication := recordPublication{coordinator: c, versions: map[string]any{}, byVersion: map[string]map[string]any{}}
	if err := publication.freezeStudy(t.Context(), RecordBundle{Study: &study}); err == nil {
		t.Fatal("mutated study became frozen publication")
	}
	if err := c.validateStudy(t.Context(), RecordBundle{Runs: []binding.ExperimentRunV1{{}}}, nil, nil, nil); err == nil {
		t.Fatal("study with no eligible retained run passed")
	}
}
func TestScientificEligibilityExcludesParentsWithCommittedReplacementDecisions(t *testing.T) {
	f := prepareReplacementRuntime(t, false)
	if _, err := f.c.Advance(t.Context(), f.options.Identity); err != nil {
		t.Fatal(err)
	}
	run, err := transportView(f.archive.run)
	if err != nil {
		t.Fatal(err)
	}
	if analysisEligible(run, map[string]any{}, f.journal.records, f.c.id) {
		t.Fatal("replaced parent remained scientifically eligible")
	}
	for _, status := range []string{"missing", "withheld"} {
		accounting := Accounting{MetricPopulations: map[string]map[string]int{}}
		summarizeMetrics(&accounting, map[string]any{"result_summaries": map[string]any{"result": map[string]any{"metric_id": "metric", "value_status": status}}}, true)
		if accounting.MetricPopulations["metric"][status+"_runs"] != 1 || accounting.MetricPopulations["metric"]["eligible_runs"] != 1 {
			t.Fatal("missing or withheld result disappeared from denominator")
		}
	}
}

package experiment

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type studyArchive struct {
	*testArchive

	study binding.ExperimentStudyV1
}

func (a *studyArchive) WriteStudy(_ context.Context, study binding.ExperimentStudyV1) error {
	a.study = study
	return nil
}
func (a *studyArchive) ReadStudy(context.Context, string, string) (binding.ExperimentStudyV1, error) {
	return a.study, nil
}
func TestRuntimeReaderOutagePreservesStartedRecordsAndArchive(t *testing.T) {
	ref := scienceReference(t)
	c, _ := scienceRuntime(t, ref)
	archive := &testArchive{runs: map[string]binding.ExperimentRunV1{}}
	reader := evidenceProvider(func(context.Context, binding.ExperimentRunV1) (EvidenceInputs, error) {
		return EvidenceInputs{}, errors.New("private evidence location")
	})
	bundle, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Metadata: map[string]RunMetadata{c.slotSnapshot()[0].entry.RunID: recordMetadataFixture(t, ref.Case.Metadata)}, Evidence: reader, Archive: archive})
	if err != nil {
		t.Fatal(err)
	}
	runID := c.slotSnapshot()[0].entry.RunID
	if bundle.ValidationByRun[runID] != termFailed || len(archive.runs) != bundle.Accounting.StartedRuns || len(bundle.Sources) != 1 {
		t.Fatal("reader outage lost records")
	}
	if !same(bundle.ValidationFailures[runID], []string{"task-evidence-validation-failed"}) {
		t.Fatal("foreign reader error entered record")
	}
}
func TestRuntimeStudyReaderOutageKeepsRunProofAndStudy(t *testing.T) {
	ref := scienceReference(t)
	c, _ := scienceRuntime(t, ref)
	reader, streams := scienceReader(t, ref)
	opened := false
	provider := evidenceProvider(func(ctx context.Context, run binding.ExperimentRunV1) (EvidenceInputs, error) {
		if opened {
			return EvidenceInputs{}, errors.New("private study location")
		}
		opened = true
		return reader.Open(ctx, run)
	})
	archive := &studyArchive{testArchive: &testArchive{runs: map[string]binding.ExperimentRunV1{}}}
	id := c.slotSnapshot()[0].entry.RunID
	bundle, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Metadata: map[string]RunMetadata{id: recordMetadataFixture(t, ref.Case.Metadata)}, Evidence: provider, Study: &ref.Definition, Archive: archive})
	if err != nil {
		t.Fatal(err)
	}
	if bundle.ValidationByRun[id] != termPassed || bundle.StudyValidation != termFailed || bundle.Study == nil || archive.study.StudyId.IsZero() {
		t.Fatal("study outage discarded run proof or study")
	}
	for _, stream := range *streams {
		if stream.closed != 1 {
			t.Fatal("run reader leaked")
		}
	}
}
func TestRuntimeDeliversFrozenRecordsToEverySuppliedArchive(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
		t.Fatal(err)
	}
	first := &testArchive{runs: map[string]binding.ExperimentRunV1{}}
	second := &testArchive{runs: map[string]binding.ExperimentRunV1{}}
	a, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Archive: first})
	if err != nil {
		t.Fatal(err)
	}
	b, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Archive: second})
	if err != nil {
		t.Fatal(err)
	}
	if len(first.runs) != 1 || len(second.runs) != 1 || !same(a.Runs, b.Runs) {
		t.Fatal("previous publication skipped a supplied archive")
	}
}
func TestRuntimeEvidenceHistoryAboveProofLimitKeepsReferencesAndSources(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	ref := recordReferences(t).Cases[1]
	source := recordSourceFixture(t, c, ref)
	attempt := decisionMap(source.Attempts[0])
	evidence := make([]binding.ExperimentEvidenceRecordV1, 1025)
	template := fixtureEvidence(t)
	for index := range evidence {
		var err error
		evidence[index], err = trialEvidence(template, source.RunID, fmt.Sprintf("evidence:configuration-%d", index))
		if err != nil {
			t.Fatal(err)
		}
	}
	observation, err := makeDecision(observationSchema, map[string]any{termExecutionAttemptID: attempt[termExecutionAttemptID], "observation": map[string]any{"kind": termConfiguration, "configurations": []any{}, termEvidence: evidence}})
	if err != nil {
		t.Fatal(err)
	}
	source.Observations = []Decision{observation}
	run, err := assembleRun(source, RunMetadata{}, c.options.Inputs.Task)
	if err != nil {
		t.Fatal(err)
	}
	view, err := transportView(run)
	if err != nil {
		t.Fatal(err)
	}
	accounting := array(at(view, "execution_accounting", "attempts"))[0]
	if len(array(at(accounting, "evidence_record_refs"))) != 1025 || len(array(at(accounting, "evidence_records"))) != 0 {
		t.Fatal("proof limit discarded evidence references")
	}
	var retained struct {
		Observation struct {
			Evidence []json.RawMessage `json:"evidence"`
		} `json:"observation"`
	}
	if json.Unmarshal(source.Observations[0].JSON(), &retained) != nil || len(retained.Observation.Evidence) != 1025 {
		t.Fatal("source history discarded evidence")
	}
}

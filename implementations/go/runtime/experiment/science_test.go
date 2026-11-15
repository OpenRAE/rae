package experiment

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type scientificReference struct {
	runtimeReferenceCompilation

	EntryID      string                     `json:"entry_id"`
	Record       json.RawMessage            `json:"record"`
	CaptureSpecs map[string]json.RawMessage `json:"capture_specs"`
	Content      string                     `json:"content"`
	Definition   binding.ExperimentStudyV1  `json:"definition"`
	Study        json.RawMessage            `json:"study"`
	Case         recordReferenceCase        `json:"case"`
}

func scienceReference(t *testing.T) scientificReference {
	t.Helper()
	raw, err := os.ReadFile("testdata/scientific-record-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference scientificReference
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("fixture")
	}
	return reference
}
func scienceRuntime(t *testing.T, ref scientificReference) (*coordinator, *testJournal) {
	t.Helper()
	input := runtimeInputFixture(t, ref.runtimeReferenceCompilation)
	j := &testJournal{}
	runtime, err := New(t.Context(), Options{Inputs: input, Identity: Identity{ActorID: "actor", AuthorizationScope: []string{termRun}}, Host: &testHost{}, Journal: j, Calls: testCalls{}, Clock: func() time.Time { return time.Date(2026, 11, 15, 10, 0, 0, 0, time.UTC) }, AdmissionBudget: time.Second, ExecutionBudget: time.Second, StoreBudget: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	c := runtimeCoordinator(t, runtime)
	for _, slot := range c.slots {
		if slot.entry.PlanEntryID == ref.EntryID {
			source := recordSourceForSlot(t, slot, ref.Case)
			j.records = append(j.records, source.Attempts...)
			j.records = append(j.records, source.Observations...)
			return c, j
		}
	}
	t.Fatal("slot missing")
	return nil, nil
}

type scientificStream struct {
	*bytes.Reader

	closed int
}

func (s *scientificStream) Close() error { s.closed++; return nil }

//nolint:ireturn // Exercise the public installed evidence-reader interface.
func scienceReader(t *testing.T, ref scientificReference) (EvidenceReader, *[]*scientificStream) {
	t.Helper()
	owner, err := experimentOwner()
	if err != nil {
		t.Fatal(err)
	}
	specs := map[string]validation.Value{}
	for key, raw := range ref.CaptureSpecs {
		specs[key], err = owner.Validate("experiment-capture-spec-v1", raw, runtimeIngress(), nil)
		if err != nil {
			t.Fatal(err)
		}
	}
	record, err := owner.Validate("experiment-evidence-record-v1", ref.Record, runtimeIngress(), nil)
	if err != nil {
		t.Fatal(err)
	}
	var view map[string]any
	if json.Unmarshal(ref.Record, &view) != nil {
		t.Fatal("fixture")
	}
	streams := []*scientificStream{}
	reader := evidenceProvider(func(context.Context, binding.ExperimentRunV1) (EvidenceInputs, error) {
		stream := &scientificStream{Reader: bytes.NewReader([]byte(ref.Content))}
		streams = append(streams, stream)
		return EvidenceInputs{Inputs: admission.ExperimentEvidenceInputs{CaptureSpecs: specs, EvidenceRecords: map[string]validation.Value{text(view, "evidence_record_id"): record}, ArtifactReaders: map[string]io.Reader{"auth-log-evidence": stream}}, Readers: []io.Closer{stream}}, nil
	})
	return reader, &streams
}
func assertScienceJSON(t *testing.T, actual any, expected json.RawMessage) {
	t.Helper()
	raw, err := json.Marshal(actual)
	if err != nil {
		t.Fatal(err)
	}
	got, err := canonjson.JCS(raw)
	if err != nil {
		t.Fatal(err)
	}
	want, err := canonjson.JCS(expected)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, want) {
		t.Fatal("scientific record differs from the independent source fixture")
	}
}
func TestRuntimeValidatesScientificEvidenceAndStudyAgainstIndependentRecords(t *testing.T) {
	ref := scienceReference(t)
	c, _ := scienceRuntime(t, ref)
	reader, streams := scienceReader(t, ref)
	metadata := recordMetadataFixture(t, ref.Case.Metadata)
	bundle, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Metadata: map[string]RunMetadata{c.slots[0].entry.RunID: metadata}, Evidence: reader, Study: &ref.Definition})
	if err != nil {
		t.Fatal(err)
	}
	if len(bundle.Runs) == 1 {
		assertScienceJSON(t, bundle.Runs[0], ref.Case.Run)
	}

	if len(bundle.Runs) != 1 || len(bundle.EligibleRunIDs) != 1 || bundle.StudyValidation != termPassed {
		t.Fatal("scientific validation refused", bundle.ValidationByRun, bundle.ValidationFailures, bundle.StudyValidation)
	}
	assertScienceJSON(t, bundle.Runs[0], ref.Case.Run)
	assertScienceJSON(t, bundle.Study, ref.Study)
	if bundle.Accounting.StartedRuns != 1 || bundle.Accounting.UnstartedRuns != 1 || bundle.Accounting.MetricPopulations["foothold-achieved"]["reported_results"] != 1 {
		t.Fatal("incorrect scientific denominator", bundle.Accounting)
	}
	for _, stream := range *streams {
		if stream.closed != 1 {
			t.Fatal("scientific reader not closed exactly once")
		}
	}
}

package experiment

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestRuntimeAccountingPreservesExactScientificOriginal(t *testing.T) {
	raw, err := readCompressedReference("testdata/record-lineage-reference.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		ExperimentID string                            `json:"experiment_id"`
		Cases        []scientificOriginalReferenceCase `json:"cases"`
	}
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("fixture")
	}
	for _, item := range reference.Cases {
		t.Run(item.Name, func(t *testing.T) { checkScientificOriginalReference(t, item, reference.ExperimentID) })
	}
}

func TestRuntimeValidatesOriginalWhilePublishingAddedAccounting(t *testing.T) {
	ref := scienceReference(t)
	c, j := scienceRuntime(t, ref)
	var original binding.ExperimentRunV1
	if json.Unmarshal(ref.Case.Run, &original) != nil {
		t.Fatal("fixture")
	}
	view, err := transportView(original)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = c.claim(t.Context(), candidateSchema, map[string]any{termExperimentID: c.id, termRun: view}); err != nil {
		t.Fatal(err)
	}
	metadata := recordMetadataFixture(t, ref.Case.Metadata)
	metadata.RunVersion = "2"
	reader, _ := scienceReader(t, ref)
	bundle, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Metadata: map[string]RunMetadata{c.slots[0].entry.RunID: metadata}, Evidence: reader, Study: &ref.Definition})
	if err != nil {
		t.Fatal(err)
	}
	if len(bundle.EligibleRunIDs) != 1 || bundle.StudyValidation != termPassed {
		t.Fatal(bundle.ValidationFailures)
	}
	raw, err := os.ReadFile("testdata/scientific-accounting-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var expected struct {
		Linked  json.RawMessage `json:"linked"`
		Checked json.RawMessage `json:"checked"`
		Study   json.RawMessage `json:"study"`
	}
	if json.Unmarshal(raw, &expected) != nil {
		t.Fatal("fixture")
	}
	assertScienceJSON(t, bundle.Runs[0], expected.Linked)
	assertScienceJSON(t, bundle.ValidationRecords[0], expected.Checked)
	assertScienceJSON(t, bundle.Study, expected.Study)
	bundle.Study = nil
	archive := &testArchive{runs: map[string]binding.ExperimentRunV1{}}
	if err = c.publishRecords(t.Context(), bundle, archive, j.records); err != nil {
		t.Fatal(err)
	}
	statuses := map[string]string{}
	for _, d := range j.records {
		m := decisionMap(d)
		if d.SchemaVersion() == publicationSchema && text(m, "state") == "published" {
			statuses[text(m, termRun, "run_version")] = text(m, "validation_status")
		}
	}
	if statuses["1"] != termPassed || statuses["2"] != termNotPerformed {
		t.Fatal("proof moved to another version", statuses)
	}
}

type scientificOriginalReferenceCase struct {
	Name    string                  `json:"name"`
	Current binding.ExperimentRunV1 `json:"current"`
	Records []json.RawMessage       `json:"records"`
	Linked  json.RawMessage         `json:"linked"`
	Checked json.RawMessage         `json:"checked"`
}

func checkScientificOriginalReference(t *testing.T, item scientificOriginalReferenceCase, experimentID string) {
	t.Helper()
	var err error

	records := make([]Decision, len(item.Records))
	for index, r := range item.Records {
		records[index], err = DecodeDecision(r)
		if err != nil {
			t.Fatal(err)
		}
	}
	originals, loadErr := canonicalArchivalRuns(records, experimentID)
	if loadErr != nil {
		t.Fatal(loadErr)
	}
	linked, checked, linkErr := accountingValidationRecord(item.Current, originals)
	if linkErr != nil {
		t.Fatal(linkErr)
	}
	assertScienceJSON(t, linked, item.Linked)
	assertScienceJSON(t, checked, item.Checked)
}

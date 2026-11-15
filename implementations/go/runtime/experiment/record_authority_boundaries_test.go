package experiment

import (
	"encoding/json"
	"maps"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestRecordApparatusContextRefusesMissingDuplicateAndStaleManifestPins(t *testing.T) {
	ref := scienceReference(t)
	c, _ := scienceRuntime(t, ref)
	source := recordSourceForSlot(t, c.slotSnapshot()[0], ref.Case)
	plan, err := transportView(source.Plan)
	if err != nil {
		t.Fatal(err)
	}
	refs := array(at(plan, "entries", c.slotSnapshot()[0].entry.PlanEntryID, "apparatus", "manifest_refs"))
	if len(refs) == 0 {
		t.Fatal("manifest authority fixture missing")
	}
	for _, field := range []string{"missing", "duplicate", "digest"} {
		t.Run(field, func(t *testing.T) { checkRecordManifestBoundary(t, c, refs, field) })
	}
	c.options.Inputs.ApparatusManifests = nil
	metadata := recordMetadataFixture(t, ref.Case.Metadata)
	bundle, readErr := c.Records(t.Context(), c.options.Identity, RecordOptions{Metadata: map[string]RunMetadata{source.RunID: metadata}})
	if readErr != nil || len(bundle.Runs) != 1 || len(bundle.EligibleRunIDs) != 0 || bundle.ValidationByRun[source.RunID] != termFailed {
		t.Fatal("missing manifest hid work or granted scientific eligibility", readErr)
	}
}
func checkRecordManifestBoundary(t *testing.T, c *coordinator, refs []any, field string) {
	t.Helper()
	options := c.options
	supplied := maps.Clone(options.Inputs.ApparatusManifests)
	defer func() { c.options = options }()
	rows := refs
	switch field {
	case "missing":
		c.options.Inputs.ApparatusManifests = nil
	case "duplicate":
		rows = append([]any{refs[0]}, refs[0])
	case "digest":
		changed := maps.Clone(object(refs[0]))
		changed[termRefDigest] = "sha256:" + strings.Repeat("0", 64)
		rows = []any{changed}
		c.options.Inputs.ApparatusManifests = supplied
	}
	result := recordContext{}
	if err := c.recordManifests(&result, rows); err == nil {
		t.Fatal("unresolved record manifest authority admitted")
	}
}
func TestRecordEvidenceInputsRequireExactCaptureAndObservedRecordOwnership(t *testing.T) {
	ref := scienceReference(t)
	c, _ := scienceRuntime(t, ref)
	source := recordSourceForSlot(t, c.slotSnapshot()[0], ref.Case)
	owner, err := experimentOwner()
	if err != nil {
		t.Fatal(err)
	}
	captures := map[string]validation.Value{}
	for id, raw := range ref.CaptureSpecs {
		value, checkErr := owner.Validate("experiment-capture-spec-v1", raw, runtimeIngress(), nil)
		if checkErr != nil {
			t.Fatal(checkErr)
		}
		captures[id] = value
	}
	record, err := owner.Validate("experiment-evidence-record-v1", ref.Record, runtimeIngress(), nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"capture-count", "capture-owner", "record-owner", "record-key", "record-content"} {
		t.Run(field, func(t *testing.T) { checkRecordEvidenceBoundary(t, c, source, captures, record, field) })
	}
}
func checkRecordEvidenceBoundary(t *testing.T, c *coordinator, source RecordSource, captures map[string]validation.Value, record validation.Value, field string) {
	t.Helper()
	inputs := admission.ExperimentEvidenceInputs{CaptureSpecs: maps.Clone(captures), EvidenceRecords: map[string]validation.Value{}}
	var view map[string]any
	if json.Unmarshal(record.JSON(), &view) != nil {
		t.Fatal("record fixture")
	}
	key := text(view, "evidence_record_id")
	inputs.EvidenceRecords[key] = record
	switch field {
	case "capture-count":
		inputs.CaptureSpecs = nil
	case "capture-owner":
		for key := range inputs.CaptureSpecs {
			inputs.CaptureSpecs[key] = validation.Value{}
		}
	case "record-owner":
		inputs.EvidenceRecords[key] = validation.Value{}
	case "record-key":
		delete(inputs.EvidenceRecords, key)
		inputs.EvidenceRecords["foreign"] = record
	case "record-content":
		source.Observations = nil
	}
	if err := c.validateEvidenceInputs(source, inputs); err == nil {
		t.Fatal("unobserved or unowned evidence supplied scientific authority")
	}
}
func TestRecordProductionRefusesConflictingEvidenceAcrossRetainedPhases(t *testing.T) {
	ref := scienceReference(t)
	c, journal := scienceRuntime(t, ref)
	var evidence map[string]any
	if json.Unmarshal(ref.Record, &evidence) != nil {
		t.Fatal("evidence fixture")
	}
	object(evidence["raw_content"])["payload_summary"] = "Changed retained evidence content."
	source := recordSourceForSlot(t, c.slotSnapshot()[0], ref.Case)
	id := text(decisionMap(source.Attempts[0]), termExecutionAttemptID)
	record, err := makeDecision(observationSchema, map[string]any{termExecutionAttemptID: id, "observation": map[string]any{"kind": termRetry, "ready": false, "evidence": []any{evidence}, "obligation_results": map[string]any{}, "verified_compensations": []any{}}})
	if err != nil {
		t.Fatal("retained retry fixture", err)
	}
	journal.records = append(journal.records, record)
	if _, err := c.Records(t.Context(), c.options.Identity, RecordOptions{}); err == nil {
		t.Fatal("conflicting phase evidence became a run record")
	}
}

func TestRecordProductionRefusesMalformedRetainedExecutionSnapshotJSON(t *testing.T) {
	ref := scienceReference(t)
	c, journal := scienceRuntime(t, ref)
	changed := false
	for index, record := range journal.records {
		if record.SchemaVersion() != observationSchema || text(decisionMap(record), "observation", "kind") != termExecution {
			continue
		}
		view := decisionMap(record)
		view["snapshot_json"] = "{"
		updated, err := makeDecision(observationSchema, view)
		if err != nil {
			t.Fatal(err)
		}
		journal.records[index] = updated
		changed = true
	}
	if !changed {
		t.Fatal("execution snapshot fixture missing")
	}
	if _, err := c.Records(t.Context(), c.options.Identity, RecordOptions{}); err == nil {
		t.Fatal("malformed retained snapshot became a run record")
	}
}

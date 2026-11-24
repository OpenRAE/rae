package experiment

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/trial"
)

// The generated carrier exposes raw JSON buffers through Value. A caller can
// mutate that buffer after decoding; each runtime handoff must recheck it.
func corruptBoundaryField(t *testing.T, field *binding.Field[json.RawMessage]) {
	t.Helper()
	if err := field.UnmarshalJSON([]byte(`{}`)); err != nil {
		t.Fatal(err)
	}
	raw, ok := field.Value()
	if !ok {
		t.Fatal("raw buffer missing")
	}
	raw[0] = '['
}
func TestRuntimeConstructionRechecksEveryMutableInputCarrierBeforeAdmission(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	for _, field := range []string{"plan", "task", "capture", "processor", "backend", "participant"} {
		t.Run(field, func(t *testing.T) { checkMutableRuntimeInputBoundary(t, c.options, field) })
	}
}
func checkMutableRuntimeInputBoundary(t *testing.T, options Options, field string) {
	t.Helper()
	input := options.Inputs
	switch field {
	case "plan":
		corruptBoundaryField(t, &input.Plan.ReplacementPolicy)
	case "task":
		corruptBoundaryField(t, &input.Task.ApparatusConstraints)
	case "capture":
		capture := binding.ExperimentCaptureSpecV1{}
		if err := capture.CaptureWindows.UnmarshalJSON([]byte(`[{}]`)); err != nil {
			t.Fatal(err)
		}
		windows, _ := capture.CaptureWindows.Value()
		windows[0][0] = '['
		input.CaptureSpecs = map[string]binding.ExperimentCaptureSpecV1{"capture": capture}
	case "processor":
		processor := binding.ProcessorManifestV2{}
		corruptBoundaryField(t, &processor.ConfigurationRegistry)
		input.ApparatusManifests = map[trial.ApparatusManifestKey]admission.ApparatusManifest{{ComponentKind: "processor"}: {Processor: &processor}}
	case "backend":
		backend := binding.BackendManifestV2{}
		corruptBoundaryField(t, &backend.ConfigurationRegistry)
		input.ApparatusManifests = map[trial.ApparatusManifestKey]admission.ApparatusManifest{{ComponentKind: "backend"}: {Backend: &backend}}
	case "participant":
		participant := binding.ParticipantImplementationManifestV1{}
		corruptBoundaryField(t, &participant.ConfigurationRegistry)
		input.ParticipantManifests = map[trial.ParticipantManifestKey]binding.ParticipantImplementationManifestV1{{ParticipantAddress: "p"}: participant}
	}
	host := &testHost{}
	options.Inputs = input
	options.Host = host
	options.Journal = &testJournal{}
	if _, err := New(t.Context(), options); err == nil {
		t.Fatal("mutated carrier admitted")
	}
	if len(host.events) != 0 {
		t.Fatal("mutable input reached installed admission")
	}
}
func TestRuntimeObservationDetachmentRefusesMutatedProofBuffers(t *testing.T) {
	for _, field := range []string{"configuration", "evidence", "cleanup-evidence", "receipt", "snapshot", "operation"} {
		t.Run(field, func(t *testing.T) {
			observation := mutatedBoundaryObservation(t, field)
			if _, err := detachObservation(observation); err == nil {
				t.Fatal("mutated observation crossed detachment")
			}
		})
	}
}
func mutatedBoundaryObservation(t *testing.T, field string) Observation {
	t.Helper()
	observation := Observation{Kind: termCapture, Complete: true}
	switch field {
	case "configuration":
		result := binding.ParticipantConfigurationResultV1{}
		if err := result.Configuration.UnmarshalJSON([]byte(`{"values":[{"value":{}}]}`)); err != nil {
			t.Fatal(err)
		}
		configuration, _ := result.Configuration.Value()
		values, _ := configuration.Values.Value()
		raw, _ := values[0].Value.Value()
		raw[0] = '['
		observation.Configurations = []binding.ParticipantConfigurationResultV1{result}
	case "evidence", "cleanup-evidence":
		evidence := binding.ExperimentEvidenceRecordV1{}
		corruptBoundaryField(t, &evidence.RawContent)
		if field == "evidence" {
			observation.Evidence = []binding.ExperimentEvidenceRecordV1{evidence}
		} else {
			observation.CleanupEvidence = []binding.ExperimentEvidenceRecordV1{evidence}
		}
	case "receipt":
		receipt := binding.TrialCleanupReceiptV1{}
		corruptBoundaryField(t, &receipt.CleanStateClaim)
		observation.CleanupReceipt = &receipt
	case "snapshot":
		corruptBoundaryField(t, &observation.Snapshot.RealizationEnvelope)
	case "operation":
		receipt := binding.OperationReceiptV1{}
		if err := receipt.Context.UnmarshalJSON([]byte(`{"parent_operation_id":{}}`)); err != nil {
			t.Fatal(err)
		}
		context, _ := receipt.Context.Value()
		raw, _ := context.ParentOperationId.Value()
		raw[0] = '['
		observation.OperationReceipts = []binding.OperationReceiptV1{receipt}
	}
	return observation
}
func TestRuntimeRecordProductionRefusesMalformedMetadataWithoutPublication(t *testing.T) {
	ref := scienceReference(t)
	c, journal := scienceRuntime(t, ref)
	for _, field := range []string{"bindings", "traceability", "participants", "invalidation", "parameters", "artifacts", "disclosures", "metrics", "foreign-metric"} {
		t.Run(field, func(t *testing.T) { checkRecordMetadataBoundary(t, c, journal, field) })
	}
}
func checkRecordMetadataBoundary(t *testing.T, c *coordinator, journal *testJournal, field string) {
	t.Helper()
	metadata := RunMetadata{}
	malformed := json.RawMessage(`{`)
	switch field {
	case "bindings":
		metadata.RealizedBindings = []json.RawMessage{malformed}
	case "traceability":
		metadata.Traceability = malformed
	case "participants":
		metadata.ParticipantImplementationProvenance = malformed
	case "invalidation":
		metadata.Invalidation = malformed
	case "parameters":
		metadata.ParameterSet = []json.RawMessage{malformed}
	case "artifacts":
		metadata.EvidenceArtifacts = []json.RawMessage{malformed}
	case "disclosures":
		metadata.RealizedFormDisclosures = []json.RawMessage{malformed}
	case "metrics":
		metadata.ResultSummaries = map[string]json.RawMessage{"metric": malformed}
	case "foreign-metric":
		metadata.ResultSummaries = map[string]json.RawMessage{"metric": json.RawMessage(`{"metric_id":"foreign"}`)}
	}
	archive := &testArchive{runs: map[string]binding.ExperimentRunV1{}}
	_, err := c.Records(t.Context(), c.options.Identity, RecordOptions{Metadata: map[string]RunMetadata{c.slots[0].entry.RunID: metadata}, Archive: archive})
	if err == nil || len(archive.events) != 0 {
		t.Fatal("malformed metadata reached publication", err)
	}
	if len(pendingPublications(journal.records, c.id)) != 0 {
		t.Fatal("malformed metadata became frozen publication")
	}
}
func TestRuntimeSourceDetachmentRefusesMutatedExecutionSnapshots(t *testing.T) {
	observation := mutatedBoundaryObservation(t, "snapshot")
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	slot := c.slotSnapshot()[0]
	source := RecordSource{Plan: slot.plan, Realization: slot.realization, ExecutionSnapshots: map[string]binding.RuntimeSnapshotV1{"attempt": observation.Snapshot}}
	if _, err := detachSource(source); err == nil {
		t.Fatal("mutated execution snapshot retained")
	}
}

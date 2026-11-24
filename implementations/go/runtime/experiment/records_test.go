package experiment

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
)

type recordReferenceCase struct {
	Name         string            `json:"name"`
	Attempts     []json.RawMessage `json:"attempts"`
	Observations []json.RawMessage `json:"observations"`
	Metadata     json.RawMessage   `json:"metadata"`
	PhaseStates  map[string]string `json:"phase_states"`
	Run          json.RawMessage   `json:"run"`
}
type recordReference struct {
	EntryID    string                `json:"entry_id"`
	Commitment string                `json:"commitment"`
	Cases      []recordReferenceCase `json:"cases"`
}

func recordReferences(t *testing.T) recordReference {
	t.Helper()
	raw, err := os.ReadFile("testdata/records-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference recordReference
	if json.Unmarshal(raw, &reference) != nil {
		t.Fatal("bad reference")
	}
	return reference
}
func recordSourceFixture(t *testing.T, c *coordinator, item recordReferenceCase) RecordSource {
	t.Helper()
	reference := recordReferences(t)
	var slot trialSlot
	for _, s := range c.slots {
		if s.entry.PlanEntryID == reference.EntryID {
			slot = s
		}
	}
	if slot.entry.PlanEntryID == "" {
		t.Fatal("entry not found")
	}
	return recordSourceForSlot(t, slot, item)
}
func recordSourceForSlot(t *testing.T, slot trialSlot, item recordReferenceCase) RecordSource {
	t.Helper()
	source := RecordSource{RunID: slot.entry.RunID, Plan: slot.plan, Realization: slot.realization, PhaseStates: item.PhaseStates}
	for _, a := range item.Attempts {
		d, decodeErr := DecodeDecision(a)
		if decodeErr != nil {
			t.Fatal(decodeErr)
		}
		source.Attempts = append(source.Attempts, d)
	}
	for _, o := range item.Observations {
		d, decodeErr := DecodeDecision(o)
		if decodeErr != nil {
			t.Fatal(decodeErr)
		}
		source.Observations = append(source.Observations, d)
	}
	return source
}
func recordMetadataFixture(t *testing.T, raw json.RawMessage) RunMetadata {
	t.Helper()
	var metadata RunMetadata
	var fields map[string]json.RawMessage
	if json.Unmarshal(raw, &fields) != nil {
		t.Fatal("metadata")
	}
	for key, target := range map[string]any{"run_version": &metadata.RunVersion, "outcome_status": &metadata.OutcomeStatus, "apparatus_context": &metadata.ApparatusContext, "evidence_artifacts": &metadata.EvidenceArtifacts, "result_summaries": &metadata.ResultSummaries, "parameter_set": &metadata.ParameterSet, "realized_bindings": &metadata.RealizedBindings, "realized_form_disclosures": &metadata.RealizedFormDisclosures} {
		if json.Unmarshal(fields[key], target) != nil {
			t.Fatal(key)
		}
	}
	if !bytes.Equal(fields["participant_implementation_provenance"], []byte("null")) {
		metadata.ParticipantImplementationProvenance = fields["participant_implementation_provenance"]
	}
	for key, target := range map[string]*json.RawMessage{"traceability": &metadata.Traceability, "invalidation": &metadata.Invalidation} {
		if value := fields[key]; len(value) > 0 && !bytes.Equal(value, []byte("null")) {
			*target = value
		}
	}
	return metadata
}
func TestRuntimeRecordsMatchIndependentAssembly(t *testing.T) {
	reference := recordReferences(t)
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	for _, item := range reference.Cases {
		t.Run(item.Name, func(t *testing.T) {
			source := recordSourceFixture(t, c, item)
			metadata := recordMetadataFixture(t, item.Metadata)
			run, err := assembleRun(source, metadata, c.options.Inputs.Task)
			if err != nil {
				t.Fatal(err)
			}
			gotRaw, _ := json.Marshal(run)
			got, _ := canonjson.JCS(gotRaw)
			want, _ := canonjson.JCS(item.Run)
			if !bytes.Equal(got, want) {
				t.Fatalf("record differs\ngot %s\nwant %s", got, want)
			}
		})
	}
}

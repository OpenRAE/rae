package admission

import (
	"encoding/json"
	"io"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestEvidenceAcquisitionRefusesMissingConflictingAndUnownedAuthorities(t *testing.T) {
	owner := boundTestOwner(t)
	var reference struct {
		Cases []experimentEvidenceReferenceCase
	}
	readFullReferenceJSON(t, "testdata/experiment-evidence-reference.json", &reference)
	for _, field := range []string{"capture-owner", "record-owner", "duplicate-requirement", "missing-requirement", "unreferenced-capture", "artifact-bound", "missing-reader", "missing-record"} {
		t.Run(field, func(t *testing.T) { checkEvidenceAcquisitionBoundary(t, owner, reference.Cases[0], field) })
	}
}
func checkEvidenceAcquisitionBoundary(t *testing.T, owner *Validator, reference experimentEvidenceReferenceCase, field string) {
	t.Helper()
	structural := schemaOnlyTestOwner(t, owner)
	admit := func(id string, raw []byte) validation.Value {
		t.Helper()
		v, err := structural.Validate(id, raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
		if err != nil {
			t.Fatal(err)
		}
		return v
	}
	task, run := decodeRuleObject(t, string(reference.Task)), decodeRuleObject(t, string(reference.Run))
	capture, record := decodeRuleObject(t, string(reference.Capture)), decodeRuleObject(t, string(reference.Record))
	captureID, recordID := stringAt(capture, "capture_spec_id"), stringAt(record, "evidence_record_id")
	input := ExperimentEvidenceInputs{CaptureSpecs: map[string]validation.Value{captureID: admit(contractExperimentCapture, reference.Capture)}, EvidenceRecords: map[string]validation.Value{recordID: admit(termExperimentEvidenceRecordV1, reference.Record)}, ArtifactReaders: map[string]io.Reader{}}
	switch field {
	case "capture-owner":
		input.CaptureSpecs[captureID] = validation.Value{}
	case "record-owner":
		input.EvidenceRecords[recordID] = validation.Value{}
	case "duplicate-requirement":
		input.CaptureSpecs["duplicate"] = input.CaptureSpecs[captureID]
	case "missing-requirement":
		input.CaptureSpecs = nil
	case "unreferenced-capture":
		object(at(run, "traceability"))["capture_spec_refs"] = []any{}
	case "artifact-bound":
		object(array(at(run, "evidence_artifacts"))[0])["size_bytes"] = json.Number("-1")
	case "missing-record":
		input.EvidenceRecords = nil
	}
	state, err := owner.prepareExperimentEvidence(task, run, input)
	if err == nil {
		err = state.validate()
	}
	if err == nil {
		t.Fatal("incomplete evidence acquisition admitted")
	}
}
func TestEvidenceRelationsRetainConcreteCaptureOwnershipAtTheRunBoundary(t *testing.T) {
	owner := boundTestOwner(t)
	var fixture struct {
		Cases []struct {
			Profile, Name string
			Document      any
		}
	}

	readFullReferenceJSON(t, "testdata/fragment-vectors.json", &fixture)
	var relation any
	for _, v := range fixture.Cases {
		if v.Profile == "experiment-evidence-requirement-relation" && v.Name == "scoped-refinement-reference" {
			relation = v.Document
			break
		}
	}
	if relation == nil {
		t.Fatal("scoped relation fixture missing")
	}
	if err := owner.experimentEvidenceRelations([]any{relation}, ExperimentEvidenceInputs{CaptureSpecs: map[string]validation.Value{"foreign": {}}}); err == nil {
		t.Fatal("unowned capture supplied relation authority")
	}
	if err := owner.experimentEvidenceRelations([]any{relation}, ExperimentEvidenceInputs{}); err == nil {
		t.Fatal("unresolved relation admitted")
	}
}
func TestEvidenceBindingsRequireExactVersionsDigestsAndMetricArtifactMembership(t *testing.T) {
	binding := evidenceBinding{requirement: "requirement", version: "1", artifactID: "artifact", digest: "sha256:abc", locator: "evidence/a.json"}
	for _, ref := range []string{`{"ref_kind":"evidence","ref_id":"requirement","ref_version":"2"}`, `{"ref_kind":"evidence","ref_id":"requirement","ref_digest":"sha256:other"}`, `{"ref_kind":"evidence","ref_id":"requirement","ref_path":"evidence/other.json"}`} {
		if evidenceBindingMatches(binding, decodeRuleObject(t, ref), map[string]bool{"artifact": true}) {
			t.Fatal("evidence identity pin was ignored")
		}
	}
	task := decodeRuleObject(t, `{"evaluation_protocol":{"metric_definitions":{"metric":{"evidence_requirements":[{"ref_kind":"evidence","ref_id":"requirement"}]}}}}`)
	if err := evidenceTaskBindings(task, map[string]any{}, map[string]evidenceBinding{}); err == nil {
		t.Fatal("metric without acquired evidence admitted")
	}
	run := decodeRuleObject(t, `{"result_summaries":{"result":{"metric_id":"metric","evidence_refs":[{"ref_kind":"evidence","ref_id":"foreign"}]}}}`)
	if err := evidenceTaskBindings(task, run, map[string]evidenceBinding{"requirement": binding}); err == nil {
		t.Fatal("metric result without required artifact membership admitted")
	}
}

type malformedBoundaryReader struct{ panicRead bool }

func (r malformedBoundaryReader) Read(buffer []byte) (int, error) {
	if r.panicRead {
		panic("private reader panic")
	}
	return len(buffer) + 1, nil
}
func TestEvidenceReadersContainPanicsAndImpossibleReadCounts(t *testing.T) {
	for _, panicRead := range []bool{false, true} {
		if _, _, err := readEvidence(malformedBoundaryReader{panicRead: panicRead}, 1, "sha256"); err == nil || strings.Contains(err.Error(), "private") {
			t.Fatal("foreign reader failure escaped", err)
		}
	}
}

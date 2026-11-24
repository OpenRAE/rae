package admission

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"io"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestExperimentEvidenceMatchesIndependentContentVerdicts(t *testing.T) {
	owner := boundTestOwner(t)
	structural := schemaOnlyTestOwner(t, owner)
	var reference struct {
		Cases []experimentEvidenceReferenceCase `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/experiment-evidence-reference.json", &reference)
	if len(reference.Cases) != 10 {
		t.Fatal("evidence reference inventory changed")
	}
	for _, ref := range reference.Cases {
		t.Run(ref.Name, func(t *testing.T) { checkExperimentEvidenceReference(t, ref, owner, structural) })
	}
}

func TestExperimentEvidenceJSONLinesKeepsCRAndCRLFBoundaries(t *testing.T) {
	for _, input := range []string{"{}\r{}", "{}\r\n{}", "{}\n{}\n"} {
		documents, err := evidenceJSONLines([]byte(input))
		if err != nil || len(documents) != 2 {
			t.Fatal("valid splitlines refused", input, err)
		}
	}
	for _, input := range []string{"", "{}\n\n{}", "{}\r\r{}"} {
		if _, err := evidenceJSONLines([]byte(input)); err == nil {
			t.Fatal("interior empty line admitted")
		}
	}
}

type experimentEvidenceReferenceCase struct {
	Name    string          `json:"name"`
	Task    json.RawMessage `json:"task"`
	Run     json.RawMessage `json:"run"`
	Capture json.RawMessage `json:"capture"`
	Record  json.RawMessage `json:"record"`
	Payload string          `json:"payload_hex"`
	Reader  bool            `json:"reader"`
	Valid   bool            `json:"valid"`
}

func checkExperimentEvidenceReference(t *testing.T, ref experimentEvidenceReferenceCase, owner *Validator, structural *validation.Validator) {
	t.Helper()

	var values [4]validation.Value
	for index, item := range []struct {
		ID   string
		Data []byte
	}{{"experiment-task-v1", ref.Task}, {termExperimentRunV1, ref.Run}, {contractExperimentCapture, ref.Capture}, {"experiment-evidence-record-v1", ref.Record}} {
		value, err := structural.Validate(item.ID, item.Data, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
		if err != nil {
			t.Fatal(err)
		}
		values[index] = value
	}
	var capture struct {
		ID string `json:"capture_spec_id"`
	}
	var record struct {
		ID string `json:"evidence_record_id"`
	}
	var run struct {
		Artifacts []struct {
			ID string `json:"artifact_id"`
		} `json:"evidence_artifacts"`
	}
	if json.Unmarshal(ref.Capture, &capture) != nil || json.Unmarshal(ref.Record, &record) != nil || json.Unmarshal(ref.Run, &run) != nil {
		t.Fatal("invalid evidence reference identities")
	}
	payload, err := hex.DecodeString(ref.Payload)
	if err != nil {
		t.Fatal(err)
	}
	inputs := ExperimentEvidenceInputs{CaptureSpecs: map[string]validation.Value{capture.ID: values[2]}, EvidenceRecords: map[string]validation.Value{record.ID: values[3]}, ArtifactReaders: map[string]io.Reader{}}
	if ref.Reader {
		inputs.ArtifactReaders[run.Artifacts[0].ID] = bytes.NewReader(payload)
	}
	err = ValidateExperimentRun(owner, values[0], values[1], &inputs)
	if (err == nil) != ref.Valid {
		t.Fatal("content verdict =", err == nil, "want", ref.Valid, err)
	}
}

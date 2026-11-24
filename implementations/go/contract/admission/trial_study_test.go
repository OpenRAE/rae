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

func TestTrialStudyMatchesIndependentEvidenceAndMembershipVerdicts(t *testing.T) {
	owner := boundTestOwner(t)
	var reference struct {
		Plan    json.RawMessage `json:"plan"`
		Task    json.RawMessage `json:"task"`
		Run     json.RawMessage `json:"run"`
		Receipt json.RawMessage `json:"receipt"`
		Capture json.RawMessage `json:"capture"`
		Record  json.RawMessage `json:"record"`
		Payload string          `json:"payload_hex"`
		Cases   []struct {
			Name     string          `json:"name"`
			Study    json.RawMessage `json:"study"`
			Valid    bool            `json:"valid"`
			Evidence bool            `json:"evidence"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/trial-study-reconciliation.json", &reference)
	structural := schemaOnlyTestOwner(t, owner)
	var err error
	values := make([]validation.Value, 6)
	for index, item := range []struct {
		ID  string
		Raw []byte
	}{{trialPlanContract, reference.Plan}, {termExperimentTaskV1, reference.Task}, {termExperimentRunV1, reference.Run}, {termTrialCleanupReceiptV1, reference.Receipt}, {contractExperimentCapture, reference.Capture}, {termExperimentEvidenceRecordV1, reference.Record}} {
		values[index], err = structural.Validate(item.ID, item.Raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
		if err != nil {
			t.Fatal(err)
		}
	}
	for _, ref := range reference.Cases {
		t.Run(ref.Name, func(t *testing.T) {
			study, err := structural.Validate(contractExperimentStudy, ref.Study, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
			if err != nil {
				t.Fatal(err)
			}
			inputs := TrialStudyInputs{Plan: values[0], Study: study, Tasks: []validation.Value{values[1]}, Runs: []validation.Value{values[2]}, CleanupReceipts: []validation.Value{values[3]}}
			if ref.Evidence {
				inputs.EvidenceByRun = trialStudyEvidence(t, reference.Payload, reference.Run, reference.Capture, reference.Record, values)
			}
			err = ValidateTrialStudy(owner, inputs)
			if (err == nil) != ref.Valid {
				t.Fatal("study verdict =", err == nil, "want", ref.Valid, err)
			}
		})
	}
}

func trialStudyEvidence(t *testing.T, encoded string, runRaw, captureRaw, recordRaw []byte, values []validation.Value) map[string]ExperimentEvidenceInputs {
	t.Helper()
	payload, checkErr := hex.DecodeString(encoded)
	if checkErr != nil {
		t.Fatal(checkErr)
	}
	run := decodeRuleObject(t, string(runRaw))
	capture := decodeRuleObject(t, string(captureRaw))
	record := decodeRuleObject(t, string(recordRaw))
	artifact := array(at(run, "evidence_artifacts"))[0]
	return map[string]ExperimentEvidenceInputs{stringAt(run, termRunID): {CaptureSpecs: map[string]validation.Value{stringAt(capture, "capture_spec_id"): values[4]}, EvidenceRecords: map[string]validation.Value{stringAt(record, "evidence_record_id"): values[5]}, ArtifactReaders: map[string]io.Reader{stringAt(artifact, termArtifactID): bytes.NewReader(payload)}}}
}

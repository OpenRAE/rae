package admission

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"io"
	"slices"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type replacementStudyReference struct {
	Root     json.RawMessage   `json:"root"`
	Study    json.RawMessage   `json:"study"`
	Tasks    []json.RawMessage `json:"tasks"`
	Runs     []json.RawMessage `json:"runs"`
	Plans    []json.RawMessage `json:"plans"`
	Receipts []json.RawMessage `json:"receipts"`
	Evidence map[string]struct {
		Captures  map[string]json.RawMessage `json:"capture_specs"`
		Records   map[string]json.RawMessage `json:"evidence_records"`
		Artifacts map[string]string          `json:"artifact_bytes"`
	} `json:"evidence"`
	Cases []struct {
		Name  string `json:"name"`
		Valid bool   `json:"valid"`
	} `json:"cases"`
}

func TestReplacementStudyRequiresCompleteRetainedHistory(t *testing.T) {
	owner := boundTestOwner(t)
	var reference replacementStudyReference
	readFullReferenceJSON(t, "testdata/replacement-study-reference.json", &reference)
	structural := schemaOnlyTestOwner(t, owner)
	value := func(id string, raw []byte) validation.Value {
		t.Helper()
		v, err := structural.Validate(id, raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
		if err != nil {
			t.Fatal(err)
		}
		return v
	}
	for _, test := range reference.Cases {
		t.Run(test.Name, func(t *testing.T) {
			checkReplacementStudyCase(t, owner, reference, test.Name, test.Valid, value)
		})
	}
}

func mutateReplacementStudy(t *testing.T, name string, runs, plans, receipts []json.RawMessage) ([]json.RawMessage, []json.RawMessage, []json.RawMessage) {
	t.Helper()
	switch name {
	case "complete":
	case "missing-parent":
		runs = runs[1:]
	case "missing-supersession":
		runs = []json.RawMessage{runs[0], runs[2]}
	case "missing-child-plan":
		plans = nil
	case "duplicate-child-plan":
		plans = append(plans, plans...)
	case "duplicate-run-version":
		runs = append(runs, runs[0])
	case "missing-cleanup":
		receipts = receipts[1:]
	case "duplicate-attempt":
		receipts = append(receipts, receipts[0])
	case "ambiguous-leaf", "unresolved-first-version":
		var payload map[string]any
		if decodeExact(runs[len(runs)-1], &payload) != nil {
			t.Fatal("bad run fixture")
		}
		payload["run_version"] = "2"
		raw, err := json.Marshal(payload)
		if err != nil {
			t.Fatal(err)
		}
		if name == "ambiguous-leaf" {
			runs = append(runs, raw)
		} else {
			runs[len(runs)-1] = raw
		}
	default:
		t.Fatal("unknown replacement reference mutation")
	}

	return runs, plans, receipts
}

func replacementStudyEvidence(t *testing.T, reference replacementStudyReference, value func(string, []byte) validation.Value) map[string]ExperimentEvidenceInputs {
	t.Helper()
	result := map[string]ExperimentEvidenceInputs{}
	for id, ref := range reference.Evidence {
		evidence := ExperimentEvidenceInputs{CaptureSpecs: map[string]validation.Value{}, EvidenceRecords: map[string]validation.Value{}, ArtifactReaders: map[string]io.Reader{}}
		for key, raw := range ref.Captures {
			evidence.CaptureSpecs[key] = value(contractExperimentCapture, raw)
		}
		for key, raw := range ref.Records {
			evidence.EvidenceRecords[key] = value(termExperimentEvidenceRecordV1, raw)
		}
		for key, encoded := range ref.Artifacts {
			raw, err := hex.DecodeString(encoded)
			if err != nil {
				t.Fatal(err)
			}
			evidence.ArtifactReaders[key] = bytes.NewReader(raw)
		}
		result[id] = evidence
	}
	return result
}

func checkReplacementStudyCase(t *testing.T, owner *Validator, reference replacementStudyReference, name string, valid bool, value func(string, []byte) validation.Value) {
	t.Helper()
	runs, plans, receipts := slices.Clone(reference.Runs), slices.Clone(reference.Plans), slices.Clone(reference.Receipts)
	runs, plans, receipts = mutateReplacementStudy(t, name, runs, plans, receipts)
	inputs := TrialStudyInputs{Plan: value(trialPlanContract, reference.Root), Study: value(contractExperimentStudy, reference.Study), EvidenceByRun: map[string]ExperimentEvidenceInputs{}}
	for _, raw := range reference.Tasks {
		inputs.Tasks = append(inputs.Tasks, value(termExperimentTaskV1, raw))
	}
	for _, raw := range runs {
		inputs.Runs = append(inputs.Runs, value(termExperimentRunV1, raw))
	}
	for _, raw := range plans {
		inputs.ReplacementPlans = append(inputs.ReplacementPlans, value(trialPlanContract, raw))
	}
	for _, raw := range receipts {
		inputs.CleanupReceipts = append(inputs.CleanupReceipts, value(termTrialCleanupReceiptV1, raw))
	}
	inputs.EvidenceByRun = replacementStudyEvidence(t, reference, value)
	err := ValidateTrialStudy(owner, inputs)
	if (err == nil) != valid {
		t.Fatal("replacement study verdict", err, "want", valid)
	}
}

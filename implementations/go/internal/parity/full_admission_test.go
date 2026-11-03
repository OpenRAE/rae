package parity

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/admission"
)

// Context-free fixture claims also exercise the complete public admission path.
// The portable corpus records no trusted external owner records. Such claims
// cannot authorize full contextual admission; their positive paths have separate
// reference-owner fixtures in the admission package.
func TestFullAdmissionCorpusBoundary(t *testing.T) {
	validator, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	cases := recordedAdmissionCases(t)
	for name, c := range cases {
		t.Run(name, func(t *testing.T) {
			id := portableAdmissionID(c.Args)
			value, err := validator.Validate(id, c.Files["input.json"], ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, nil)
			expected := portableRecordedAdmission(t, c) && !fullAdmissionNeedsOwner(id)
			if (err == nil) != expected {
				t.Fatalf("full admission=%v reference local claim=%v owner required=%v error=%v", err == nil, portableRecordedAdmission(t, c), fullAdmissionNeedsOwner(id), err)
			}
			if err != nil && (value.ContractID() != "" || len(value.JSON()) != 0) {
				t.Fatal("refusal returned admitted data")
			}
		})
	}
}

func fullAdmissionNeedsOwner(id string) bool {
	switch id {
	case "experiment-run-v1", "experiment-apparatus-context-v1", "experiment-study-v1", "associated-artifact-manifest-v1", "behavioral-relation-profile-v1", "scientific-completeness-assessment-v1", "backend-materialization-attestation-v1", "backend-runtime-descendants-v1", "materialization-archive-record-v1", "materialized-scenario-v1", "participant-control-occurrence-v1", "participant-control-occurrence-v2", "participant-crossing-occurrence-v1":
		return true
	default:
		return false
	}
}

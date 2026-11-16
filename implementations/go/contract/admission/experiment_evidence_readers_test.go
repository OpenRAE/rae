package admission

import (
	"io"
	"testing"
)

type singleInspectionEOFError struct{ calls int }

func (*singleInspectionEOFError) Error() string { return "private-reader-error" }
func (e *singleInspectionEOFError) Is(target error) bool {
	e.calls++
	if e.calls > 1 {
		panic("reader error inspected twice")
	}
	return target == io.EOF
}

type finalEvidenceReader struct {
	data    []byte
	failure error
}

func (r finalEvidenceReader) Read(buffer []byte) (int, error) { return copy(buffer, r.data), r.failure }
func TestExperimentEvidenceNormalizesForeignEOFAfterOneInspection(t *testing.T) {
	failure := &singleInspectionEOFError{}
	data, _, err := readEvidence(finalEvidenceReader{data: []byte("proof"), failure: failure}, 5, "sha256")
	if err != nil || string(data) != "proof" || failure.calls != 1 {
		t.Fatal("foreign EOF escaped the reader boundary", err, failure.calls)
	}
}

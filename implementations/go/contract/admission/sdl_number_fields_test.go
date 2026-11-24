package admission

import "testing"

func TestRuntimeNumericFieldRecords(t *testing.T) {
	for _, operation := range []string{"integer", "integer::", "integer:x:2", "integer:2:1", "integer:0.5:2", "number:2:1", "number:0:NaN"} {
		if sdlNumberOperation(operation) {
			t.Errorf("accepted malformed operation %q", operation)
		}
	}
	if !sdlNumberOperation("number:0.5:1.5") {
		t.Fatal("refused fractional numeric bounds")
	}
}

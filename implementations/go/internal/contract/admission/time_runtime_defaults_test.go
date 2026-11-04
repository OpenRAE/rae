package admission

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestRuntimeClockPythonDefaults(t *testing.T) {
	var recording struct {
		Reference string `json:"reference"`
		Cases     []struct {
			Name     string          `json:"name"`
			Input    json.RawMessage `json:"input"`
			Admitted bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/clock-default-verdicts.json", &recording)
	if recording.Reference != "TimeRuntimeStateModel.model_validate" || len(recording.Cases) != 98 {
		t.Fatal("unexpected clock reference")
	}
	e := boundTestOwner(t)
	for _, c := range recording.Cases {
		for _, id := range []string{termTimeRuntimeStateV1, termRuntimeSnapshotV1} {
			t.Run(id+"/"+c.Name, func(t *testing.T) {
				input := c.Input
				if id == termRuntimeSnapshotV1 {
					input = controlJSON(t, map[string]any{"schema_version": "runtime-snapshot/v1", "time_model_state": input})
				}
				checkRuntimeClockReference(t, e, id, input, c.Admitted)
			})
		}
	}
}

func checkRuntimeClockReference(t *testing.T, e *Validator, id string, input []byte, admitted bool) {
	t.Helper()
	original := bytes.Clone(input)
	value, err := e.Validate(id, input, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, nil)
	if (err == nil) != admitted {
		t.Fatalf("Python admitted=%v: %v", admitted, err)
	}
	if !bytes.Equal(input, original) {
		t.Fatal("validation mutated input")
	}
	if err == nil && !bytes.Equal(value.JSON(), original) {
		t.Fatal("defaults changed admitted evidence")
	}
	if err != nil && (value.ContractID() != "" || len(value.JSON()) != 0) {
		t.Fatal("refusal returned data")
	}
}

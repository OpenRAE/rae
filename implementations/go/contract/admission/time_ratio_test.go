package admission

import (
	"bytes"
	"fmt"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestTimingLimitReducedRatiosMatchPython(t *testing.T) {
	var reference struct {
		Cases []struct {
			Contract    string `json:"contract"`
			Numerator   int    `json:"numerator"`
			Denominator int    `json:"denominator"`
			Admitted    bool   `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/time-ratio-verdicts.json", &reference)
	if len(reference.Cases) != 18 {
		t.Fatal("timing ratio inventory changed")
	}
	e := boundTestOwner(t)
	owner := fullExperimentOwner(loadFullReferenceOwners(t), "experiment")
	for _, c := range reference.Cases {
		t.Run(fmt.Sprintf("%s/%d-%d", c.Contract, c.Numerator, c.Denominator), func(t *testing.T) {
			model := fixtureObject(t, "fixtures/time/realized-time-model-v1/valid/reference.json")
			model["timing_limits"] = []any{map[string]any{"limit_id": "resolution", "subject_address": "time.clock.logical", "kind": "resolution", "value": map[string]any{"numerator": c.Numerator, "denominator": c.Denominator}, "unit": "seconds", "evidence_refs": []any{"evidence:time-readback"}}}
			value := model
			var context any
			if c.Contract == termExperimentRunV1 {
				value = fixtureObject(t, "fixtures/experiment-core/experiment-run-v1/valid/reference.json")
				model["run_id"] = value["run_id"]
				value["realized_time_model"] = model
				context = owner
			}
			raw := controlJSON(t, value)
			admitted, err := e.Validate(c.Contract, raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, context)
			if (err == nil) != c.Admitted {
				t.Fatalf("Python admitted=%v: %v", c.Admitted, err)
			}
			checkTimingRatioEvidence(t, admitted.ContractID(), admitted.JSON(), raw, err)
		})
	}
}

func checkTimingRatioEvidence(t *testing.T, id string, admitted, original []byte, err error) {
	t.Helper()
	if err == nil && !bytes.Equal(admitted, original) {
		t.Fatal("ratio validation changed evidence")
	}
	if err != nil && id != "" {
		t.Fatal("refusal returned admitted data")
	}
}

package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestResourcePoolLedgerMatchesIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Name     string          `json:"name"`
			Input    json.RawMessage `json:"input"`
			Admitted bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/pool-verdicts.json", &reference)
	if len(reference.Cases) != 108 {
		t.Fatal("independent pool inventory changed")
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			err := checkReferencePool(e, c.Input)
			if (err == nil) != c.Admitted {
				t.Fatalf("pool model differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

func checkReferencePool(e *Validator, raw []byte) error {
	value, err := e.low.DefaultedObjectFragment(termRuntimeSnapshotV1, "#/$defs/ParticipantResourcePoolStateModel", raw, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64})
	if err == nil {
		err = resourcePoolState(value)
	}
	if err == nil {
		for _, allocation := range object(at(value, "allocations")) {
			_, err = e.resourceModel("ParticipantResourcePoolAllocationModel", allocation)
			if err != nil {
				break
			}
		}
	}
	return err
}

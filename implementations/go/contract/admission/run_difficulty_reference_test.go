package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestArchivalDifficultyTimingMatchesIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Name     string
			Value    json.RawMessage
			Admitted bool
		}
	}
	readFullReferenceJSON(t, "testdata/run-difficulty-verdicts.json", &reference)
	if len(reference.Cases) != 28 {
		t.Fatal("difficulty timing inventory changed", len(reference.Cases))
	}
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			err := runDifficulty(validation.Invocation{Instance: decodeRuleObject(t, string(c.Value))})
			if (err == nil) != c.Admitted {
				t.Fatalf("archival difficulty differs from native admission (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

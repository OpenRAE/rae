package admission

import (
	"encoding/json"
	"testing"
)

func TestStudyConditionMatchingAgainstIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Baselines map[string]json.RawMessage `json:"baselines"`
		Cases     []struct {
			Baseline   string          `json:"baseline"`
			Name       string          `json:"name"`
			Assignment json.RawMessage `json:"assignment"`
			Admitted   bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/condition-verdicts.json", &reference)
	if len(reference.Cases) != 135 || len(reference.Baselines) != 3 {
		t.Fatal("independent study condition inventory changed")
	}
	for _, c := range reference.Cases {
		t.Run(c.Baseline+"/"+c.Name, func(t *testing.T) {
			run := decodeRuleObject(t, string(reference.Baselines[c.Baseline]))
			assignment := decodeRuleObject(t, string(c.Assignment))
			if admitted := runCondition(run, assignment); admitted != c.Admitted {
				t.Fatalf("condition match=%v, Python=%v", admitted, c.Admitted)
			}
		})
	}
}

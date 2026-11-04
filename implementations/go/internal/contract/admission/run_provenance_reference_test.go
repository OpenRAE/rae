package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestTrialRunProvenanceBindingsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Name     string          `json:"name"`
			Value    json.RawMessage `json:"value"`
			Admitted bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/provenance-verdicts.json", &reference)
	if len(reference.Cases) != 26 {
		t.Fatal("independent trial-provenance inventory changed")
	}
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			err := runTrialProvenance(validation.Invocation{Instance: decodeRuleObject(t, string(c.Value))})
			if (err == nil) != c.Admitted {
				t.Fatalf("trial linkage differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

type difficultyBindingTestContext struct {
	design    []byte
	condition string
}

func (c difficultyBindingTestContext) ExperimentDesign() []byte { return c.design }
func (c difficultyBindingTestContext) ConditionID() string      { return c.condition }

func TestDifficultyAuthoringBindingsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	var reference struct {
		Cases []struct {
			Name      string          `json:"name"`
			Spec      json.RawMessage `json:"spec"`
			Run       json.RawMessage `json:"run"`
			Condition string          `json:"condition"`
			Admitted  bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/difficulty-binding-verdicts.json", &reference)
	if len(reference.Cases) != 17 {
		t.Fatal("independent difficulty-authoring inventory changed")
	}
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			err := e.difficultyAuthoring(validation.Invocation{Instance: decodeRuleObject(t, string(c.Run)), Context: difficultyBindingTestContext{c.Spec, c.Condition}})
			if (err == nil) != c.Admitted {
				t.Fatalf("difficulty authoring differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

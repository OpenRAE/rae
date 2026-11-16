package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestTrialSupersessionPreservesIndependentArchivalVersions(t *testing.T) {
	owner := boundTestOwner(t)
	var ref struct {
		Cases []struct {
			Name     string          `json:"name"`
			Run      json.RawMessage `json:"run"`
			Child    json.RawMessage `json:"child"`
			Expected json.RawMessage `json:"superseded"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/replacement-archive-reference.json", &ref)
	for _, test := range ref.Cases {
		t.Run(test.Name, func(t *testing.T) {
			child, err := owner.Validate(trialPlanContract, test.Child, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
			if err != nil {
				t.Fatal(err)
			}
			actual, err := SupersedeTrialRunJSON(owner, test.Run, child)
			if err != nil {
				t.Fatal(err)
			}
			a, e1 := canonjson.JCS(actual)
			b, e2 := canonjson.JCS(test.Expected)
			if e1 != nil || e2 != nil || string(a) != string(b) {
				t.Fatal("superseded archival content differs")
			}
		})
	}
}

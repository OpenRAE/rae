package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestControlModelRulesCheckPublishedEvaluations(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct{ id, name string }{
		{"participant-control-evaluation-v1", "teaching-inject"},
		{"participant-control-evaluation-v1", "conflict"},
		{"participant-control-evaluation-v1", "downgrade"},
		{"participant-control-evaluation-v2", "dependency-chain"},
		{"participant-control-evaluation-v2", "optional-failure"},
		{"participant-control-evaluation-v2", "later-phase-denial"},
		{"participant-control-evaluation-v2", "owner-flow"},
	} {
		t.Run(test.id+"/"+test.name, func(t *testing.T) {
			root := fixtureObject(t, "fixtures/participant-runtime/"+test.id+"/valid/"+test.name+".json")
			if err := e.checkModels(test.id, controlJSON(t, root), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}); err != nil {
				t.Fatal(err)
			}
			controlModelRefusesAbsentResult(t, e, test.id, root)
		})
	}
}

func controlModelRefusesAbsentResult(t *testing.T, e *Validator, id string, root map[string]any) {
	t.Helper()
	results := array(root["results"])
	if len(results) == 0 {
		t.Fatal("fixture has no contributor")
	}
	result := object(results[0])
	result["status"], result["payload"] = "resolved", nil
	if id == "participant-control-evaluation-v2" {
		result["rule_outcome"], result["evaluated_basis"] = nil, []any{}
	}
	raw := controlJSON(t, root)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err := e.low.CheckSchema(id, raw, limits); err != nil {
		t.Fatalf("mutation must retain schema shape: %v", err)
	}
	if err := e.checkModels(id, raw, limits); err == nil {
		t.Error("accepted resolved contributor without a typed result")
	}
}

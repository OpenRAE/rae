package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestOpacityCarrierAndEvidence(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct{ id, rule, name string }{
		{"participant-opacity-analysis-input-v1", "participant-opacity-finite-carrier-counts", "opaque-pair"},
		{"participant-opacity-model-check-input-v1", "participant-opacity-model-check-graph-joins", "opaque-transition-model"},
		{"participant-opacity-analysis-evidence-v1", "participant-opacity-evidence-joins", "bounded-counterexample"},
		{"participant-opacity-model-check-evidence-v1", "participant-opacity-model-check-evidence-joins", "opaque-transition-model"},
	} {
		t.Run(test.id, func(t *testing.T) {
			v := fixtureObject(t, "fixtures/formal-analysis/"+test.id+"/valid/"+test.name+".json")
			rule, ok := e.checker(test.rule)
			if !ok {
				t.Fatal("missing rule", test.rule)
			}
			if err := rule.check(validation.Invocation{Instance: v}); err != nil {
				t.Fatal(err)
			}
			alterOpacityCountOrDigest(v)
			if err := rule.check(validation.Invocation{Instance: v}); err == nil {
				t.Error("accepted inconsistent counts or checker digest")
			}
		})
	}
}

func alterOpacityCountOrDigest(v map[string]any) {
	if at(v, "declared_counts") != nil {
		for key := range object(v["declared_counts"]) {
			object(v["declared_counts"])[key] = json.Number("999")
			break
		}
	} else {
		v["checker_configuration_digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	}
}

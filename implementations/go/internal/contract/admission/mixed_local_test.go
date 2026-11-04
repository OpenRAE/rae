package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestMixedCompositionAndBackendLocalRules(t *testing.T) {
	e := boundTestOwner(t)
	for _, name := range []string{"alternative", "simultaneous-mixed", "staged"} {
		v := fixtureObject(t, "fixtures/plans/mixed-participant-composition-profile-v1/valid/"+name+".json")
		if err := e.mixedCompositionLocal(validation.Invocation{Instance: v}); err != nil {
			t.Errorf("%s: %v", name, err)
		}
		v["initial_phase_id"] = "missing"
		if err := e.mixedCompositionLocal(validation.Invocation{Instance: v}); err == nil {
			t.Error("accepted missing initial phase")
		}
	}
	for _, name := range []string{"mixed-edge", "mixed-handoff"} {
		v := fixtureObject(t, "fixtures/control-plane/mixed-backend-execution-binding-v1/valid/"+name+".json")
		if err := mixedBackendLocal(validation.Invocation{Key: validation.Key{ContractID: "mixed-backend-execution-binding-v1"}, Instance: v}); err != nil {
			t.Fatal(err)
		}
		subject := object(v["subject"])
		subject["time"] = map[string]any{"coordinator": subject["bridge"]}
		if name == "mixed-handoff" {
			object(subject["time"])["coordinator"] = subject["transfer"]
		}
		if err := mixedBackendLocal(validation.Invocation{Key: validation.Key{ContractID: "mixed-backend-execution-binding-v1"}, Instance: v}); err == nil {
			t.Error("accepted one service in two independent roles")
		}
	}
	stage := fixtureObject(t, "fixtures/control-plane/mixed-backend-stage-report-v1/valid/mixed-edge-02.json")
	if err := mixedBackendLocal(validation.Invocation{Key: validation.Key{ContractID: "mixed-backend-stage-report-v1"}, Instance: stage}); err != nil {
		t.Fatal(err)
	}
	object(stage["stage"])["evidence_refs"] = []any{}
	if err := mixedBackendLocal(validation.Invocation{Key: validation.Key{ContractID: "mixed-backend-stage-report-v1"}, Instance: stage}); err == nil {
		t.Error("accepted known execution without evidence")
	}
}

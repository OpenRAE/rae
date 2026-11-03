package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestFactorialAuthoringPreparationAndSuppliedAgreement(t *testing.T) {
	e := boundTestOwner(t)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	// Independently recorded from the Python model's JCS projection of the published fixtures.
	for _, test := range []struct {
		name, digest string
		conditions   int
	}{
		{"factorial", "sha256:8e6ac7476ff36e956ab1f32871dcaad7b0c0ae0d08e3e949abb06db67461e197", 4},
		{"typed-factorial", "sha256:3b36520a3964d8b3b84fdcd1ec17a13681eb9f91d28177b11f48bed35ca89d00", 4},
		{"typed-factorial-selection-only", "sha256:c1519fada9e1dd0a64d466c83d48bf9ba011b54fb95ce77c2044f8d685378f9b", 2},
	} {
		t.Run(test.name, func(t *testing.T) {
			v := fixtureObject(t, "fixtures/experiment-core/experiment-authoring-input-v1/valid/"+test.name+".json")
			normal := factorialPreparedFixture(t, e, v, limits)
			if len(object(at(normal, "run_plan", "allocation", "condition_assignments"))) != test.conditions {
				t.Error("condition count differs")
			}
			digest, err := jsonDigest(map[string]any{"allocation": at(normal, "run_plan", "allocation"), "bindings": at(normal, "binding_descriptors")})
			if err != nil || digest != test.digest {
				t.Fatalf("projection digest=%s err=%v", digest, err)
			}
			factorialRefusesConflicts(t, e, v, normal, limits)
		})
	}
}

func factorialPreparedFixture(t *testing.T, e *Validator, v any, limits ingress.Limits) any {
	t.Helper()
	raw := controlJSON(t, v)
	if err := e.CheckPortable("experiment-authoring-input-v1", raw, limits); err != nil {
		t.Fatal(err)
	}
	prepared, err := e.prepare("experiment-authoring-input-v1", raw, limits)
	if err != nil {
		t.Fatal(err)
	}
	if err = e.CheckPortable("experiment-authoring-input-v1", prepared, limits); err != nil {
		t.Fatal(err)
	}
	normal, err := ingress.Parse(prepared, limits, ingress.Object)
	if err != nil {
		t.Fatal(err)
	}
	return normal
}

func factorialRefusesConflicts(t *testing.T, e *Validator, v, normal any, limits ingress.Limits) {
	t.Helper()
	for _, assignment := range object(at(normal, "run_plan", "allocation", "condition_assignments")) {
		object(assignment)["description"] = "contradictory supplied materialization"
		break
	}
	if err := e.CheckPortable("experiment-authoring-input-v1", controlJSON(t, normal), limits); err == nil {
		t.Error("accepted changed supplied allocation")
	}
	object(at(v, "factorial_design"))["condition_bound"] = json.Number("1")
	if err := e.CheckPortable("experiment-authoring-input-v1", controlJSON(t, v), limits); err == nil {
		t.Error("expanded beyond condition bound")
	}
}

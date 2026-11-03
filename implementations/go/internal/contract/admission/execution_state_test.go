package admission

import (
	"encoding/json"
	"maps"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestExecutionServiceStateModel(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct {
		name    string
		changes map[string]any
		valid   bool
	}{
		{"reference", nil, true},
		{"capacity overrun", map[string]any{"reserved": json.Number("4"), "in_flight": json.Number("1"), "capacity": json.Number("4")}, false},
		{"future observed generation", map[string]any{"generation": json.Number("1"), "observed_generation": json.Number("2")}, false},
		{"admitting while paused", map[string]any{"accepting_new_work": true, "observed_lifecycle": "paused"}, false},
		{"admitting while unready", map[string]any{"accepting_new_work": true, "readiness": "not_ready"}, false},
		{"draining disagreement", map[string]any{"draining": true, "observed_lifecycle": "running"}, false},
		{"release disagreement", map[string]any{"resources_released": true, "observed_lifecycle": "running"}, false},
		{"quiescent reservation", map[string]any{"quiescent": true, "reserved": json.Number("1")}, false},
		{"duplicate evidence", map[string]any{"evidence_refs": []any{"e", "e"}}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			root := fixtureObject(t, "fixtures/participant-runtime/participant-execution-service-state-v1/valid/running-ready.json")
			maps.Copy(root, test.changes)
			raw, err := json.Marshal(root)
			if err != nil {
				t.Fatal(err)
			}
			checkErr := e.CheckPortable("participant-execution-service-state-v1", raw, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64})
			if (checkErr == nil) != test.valid {
				t.Errorf("CheckPortable() = %v, want valid=%v", checkErr, test.valid)
			}
		})
	}
}

package parity

import (
	"context"
	"encoding/json"
	"testing"
)

func TestCoverageRequiresImplementedRunners(t *testing.T) {
	run := func(context.Context, Case) (json.RawMessage, error) { return json.RawMessage(`{}`), nil }
	cases := []Case{{Surface: "cli", Command: "semantic parse"}}
	key := cases[0].Key()
	for _, test := range []struct {
		name        string
		registered  map[string]Runner
		implemented []string
		complete    bool
		wantError   bool
	}{
		{"unported", nil, nil, false, false},
		{"implemented", map[string]Runner{key: run}, []string{key}, false, false},
		{"complete", map[string]Runner{key: run}, []string{key}, true, false},
		{"removed runner", nil, []string{key}, false, true},
		{"nil runner", map[string]Runner{key: nil}, []string{key}, false, true},
		{"no cases", map[string]Runner{"cli other": run}, []string{"cli other"}, false, true},
		{"untracked runner", map[string]Runner{key: run}, nil, false, true},
		{"duplicate inventory", map[string]Runner{key: run}, []string{key, key}, false, true},
		{"incomplete cutover", nil, nil, true, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			err := checkCoverage(cases, test.registered, test.implemented, test.complete)
			if got := err != nil; got != test.wantError {
				t.Errorf("checkCoverage() failed = %t, want %t; error = %v", got, test.wantError, err)
			}
		})
	}
}

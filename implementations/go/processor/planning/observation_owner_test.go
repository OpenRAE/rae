package planning

import "testing"

func TestObservationOwnerFollowsActionableBackendPriority(t *testing.T) {
	for _, test := range []struct {
		name       string
		operations map[string][]planOperation
		want       string
	}{
		{"empty", nil, termProvisioning},
		{"unchanged", map[string][]planOperation{termOrchestration: {{Action: termUnchanged}}, termEvaluation: {{Action: termUnchanged}}}, termProvisioning},
		{"evaluation", map[string][]planOperation{termOrchestration: {{Action: termUnchanged}}, termEvaluation: {{Action: "create"}}}, termEvaluation},
		{"orchestration", map[string][]planOperation{termOrchestration: {{Action: "create"}}, termEvaluation: {{Action: "create"}}}, termOrchestration},
	} {
		t.Run(test.name, func(t *testing.T) {
			p := executionPlan{operations: test.operations}
			if got := p.ObservationOwner(); got != test.want {
				t.Fatalf("owner=%q, want %q", got, test.want)
			}
		})
	}
}

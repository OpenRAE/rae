package admission

import (
	"encoding/json"
	"os"
	"testing"
)

// The cases follow parallelism_bounds in raes_contracts.trial_parallelism.
func TestTrialParallelismBoundsFollowTheReference(t *testing.T) {
	for name, test := range map[string]struct {
		intent       map[string]any
		entries      int
		lower, upper int
		refused      bool
	}{
		"absent":              {nil, 9, 1, 1, false},
		"open":                {map[string]any{"posture": "open"}, 3, 1, 3, false},
		"open over maximum":   {map[string]any{"posture": "open"}, maxTrialParallelism + 5, 1, maxTrialParallelism, false},
		"exact":               {map[string]any{"posture": postureExact, "count": json.Number("2")}, 4, 2, 2, false},
		"constrained":         {map[string]any{"posture": "constrained", "minimum": json.Number("2"), "maximum": json.Number("3")}, 9, 2, 3, false},
		"constrained no max":  {map[string]any{"posture": "constrained", "minimum": json.Number("2")}, 4, 2, 4, false},
		"constrained zero":    {map[string]any{"posture": "constrained", "minimum": json.Number("0")}, 4, 1, 4, false},
		"minimum over trials": {map[string]any{"posture": "constrained", "minimum": json.Number("5")}, 4, 0, 0, true},
	} {
		lower, upper, err := trialParallelismBounds(test.intent, test.entries)
		if (err != nil) != test.refused || lower != test.lower || upper != test.upper {
			t.Errorf("%s: bounds = %d, %d, %v", name, lower, upper, err)
		}
	}
}

// The cases follow TrialFactModel, TrialOperationModel and TrialOutcomeModel
// in raes_contracts.assigned_trial.
func TestTrialOutcomeKeepsOriginalObservations(t *testing.T) {
	snapshot := map[string]any{"schema_version": "runtime-snapshot/v1"}
	execution := map[string]any{"observation": map[string]any{"kind": termExecution, "ceased": true, "state": "succeeded"}, "execution_snapshot": snapshot}
	cleanup := map[string]any{"observation": map[string]any{"kind": "cleanup"}}
	operation := func(id, context string) map[string]any {
		return map[string]any{"receipt": map[string]any{"operation_id": id, "context": context}, "status": map[string]any{"operation_id": id, "context": context}}
	}
	for name, test := range map[string]struct {
		outcome map[string]any
		valid   bool
	}{
		"completed":                 {map[string]any{"progress": statusCompleted, "facts": []any{execution, cleanup}, "operations": []any{operation("a", "x"), operation("b", "x")}}, true},
		"pending":                   {map[string]any{"progress": "pending", "facts": []any{cleanup}}, true},
		"completed without cleanup": {map[string]any{"progress": statusCompleted, "facts": []any{execution}}, false},
		"duplicate kinds":           {map[string]any{"progress": "pending", "facts": []any{cleanup, cleanup}}, false},
		"duplicate operations":      {map[string]any{"progress": "pending", "operations": []any{operation("a", "x"), operation("a", "x")}}, false},
		"status differs": {map[string]any{"progress": "pending", "operations": []any{map[string]any{
			"receipt": map[string]any{"operation_id": "a", "context": "x"}, "status": map[string]any{"operation_id": "a", "context": "y"},
		}}}, false},
		"execution without snapshot": {map[string]any{"progress": "pending", "facts": []any{map[string]any{"observation": map[string]any{"kind": termExecution, "ceased": true, "state": "succeeded"}}}}, false},
		"snapshot on cleanup":        {map[string]any{"progress": "pending", "facts": []any{map[string]any{"observation": map[string]any{"kind": "cleanup"}, "execution_snapshot": snapshot}}}, false},
		"execution not ceased":       {map[string]any{"progress": "pending", "facts": []any{map[string]any{"observation": map[string]any{"kind": termExecution, "ceased": false, "state": "succeeded"}, "execution_snapshot": snapshot}}}, false},
		"execution running":          {map[string]any{"progress": "pending", "facts": []any{map[string]any{"observation": map[string]any{"kind": termExecution, "ceased": true, "state": "running"}, "execution_snapshot": snapshot}}}, false},
	} {
		if err := trialOutcomeLocal(test.outcome); (err == nil) != test.valid {
			t.Errorf("%s: trial outcome error = %v; want valid=%t", name, err, test.valid)
		}
	}
}

// The expected size is the reference compiler charge: the canonical bytes of
// the sealed AdmittedTrialEntryModel and its TrialCleanupPlanModel.
func TestTrialEntryRetainedBytesMatchesReferenceCharge(t *testing.T) {
	raw, err := os.ReadFile("../../../../contracts/fixtures/control-plane/assigned-trial-v1/valid/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Plan struct {
			Entries map[string]json.RawMessage `json:"entries"`
			Cleanup map[string]json.RawMessage `json:"cleanup_plans"`
		} `json:"plan"`
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	entry, cleanup := fixture.Plan.Entries["entry-a"], fixture.Plan.Cleanup["cleanup-a"]
	if size, err := TrialEntryRetainedBytes(owner, entry, cleanup); err != nil || size != 3151 {
		t.Fatalf("retained bytes = %d, %v; want 3151", size, err)
	}
	for name, test := range map[string]struct {
		owner          *Validator
		entry, cleanup []byte
	}{
		"no owner":        {nil, entry, cleanup},
		"malformed entry": {owner, []byte(`[`), cleanup},
		"invalid entry":   {owner, []byte(`{"plan_entry_id":""}`), cleanup},
		"invalid cleanup": {owner, entry, []byte(`{}`)},
	} {
		if _, err := TrialEntryRetainedBytes(test.owner, test.entry, test.cleanup); err == nil {
			t.Errorf("%s: retained bytes accepted", name)
		}
	}
}

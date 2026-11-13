package admission

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func preparationOperationsFixture(t *testing.T, operations, members int) binding.ProvisioningPlanV1 {
	t.Helper()
	values := make([]int, members)
	entries := make([]map[string]any, operations)
	for i := range entries {
		entries[i] = map[string]any{"action": "create", "address": "provision.node.host", "resource_type": "node", "payload": map[string]any{"items": values}, "ordering_dependencies": []string{}, "refresh_dependencies": []string{}}
	}
	raw, err := json.Marshal(map[string]any{"operations": entries})
	if err != nil {
		t.Fatal(err)
	}
	var plan binding.ProvisioningPlanV1
	if json.Unmarshal(raw, &plan) != nil {
		t.Fatal("plan fixture")
	}
	return plan
}
func TestPreparationOperationsRetainTheSmallerAggregateBudget(t *testing.T) {
	for _, test := range []struct {
		members  int
		accepted bool
	}{{200, true}, {400, false}} {
		plan := preparationOperationsFixture(t, 200, test.members)
		err := CheckPreparationOperations(plan)
		if (err == nil) != test.accepted {
			t.Fatalf("members=%d admitted=%v err=%v", test.members, err == nil, err)
		}
	}
}
func TestPreparationOperationsRetainIndividualPayloadLimits(t *testing.T) {
	for _, test := range []struct {
		members  int
		accepted bool
	}{{4094, true}, {4096, false}} {
		err := CheckPreparationOperations(preparationOperationsFixture(t, 1, test.members))
		if (err == nil) != test.accepted {
			t.Fatalf("payload members=%d admitted=%v err=%v", test.members, err == nil, err)
		}
	}
	plan := preparationOperationsFixture(t, 1, 1)
	operations, _ := plan.Operations.Value()
	payload, _ := operations[0].Payload.Value()
	payload["value"] = json.RawMessage(`"` + strings.Repeat("x", 4097) + `"`)
	if err := CheckPreparationOperations(plan); err == nil {
		t.Fatal("payload scalar limit lost")
	}
}

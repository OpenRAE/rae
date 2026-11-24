package planning

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func TestPhaseProjectionRefusesAggregateBeforeEncoding(t *testing.T) {
	payload := json.RawMessage(`{"value":"` + strings.Repeat("x", 750000) + `"}`)
	operations := make([]planOperation, 12)
	for i := range operations {
		operations[i] = planOperation{Address: fmt.Sprintf("provision.node.host%d", i), Action: termCreate, Kind: "node", Payload: payload}
	}
	var output binding.ProvisioningPlanV1
	err := emitPhase("provisioning-plan-v1", map[string]any{"operations": operations}, &output)
	if !errors.Is(err, value.ErrLimit) || output.Operations.Present() {
		t.Fatalf("oversized phase published before refusal: %v", err)
	}
}

func TestAssumedSnapshotUsesRuntimeAggregateBudget(t *testing.T) {
	payload := json.RawMessage(`{"values":[` + strings.Repeat("0,", 127) + `0]}`)
	plan := &executionPlan{resources: map[string]plannedResource{}, operations: map[string][]planOperation{}}
	for i := range 600 {
		address := fmt.Sprintf("provision.node.host%d", i)
		plan.operations[termProvisioning] = append(plan.operations[termProvisioning], planOperation{Address: address, Action: termCreate, Kind: "node", Payload: payload})
	}
	snapshot, err := AssumedSnapshot(plan)
	if !errors.Is(err, value.ErrLimit) || snapshot.Entries.Present() {
		t.Fatalf("assumed snapshot bypassed runtime node budget: %v", err)
	}
}

func TestOnlyDeclaredSourceGetsDocumentTextCeiling(t *testing.T) {
	raw := json.RawMessage(`{"snapshot":"` + strings.Repeat("x", value.Runtime().MaxScalarBytes+1) + `"}`)
	declared := map[string]any{"materialization_source": materializationSourceWire(raw)}
	if err := value.ValidateProjected(declared, value.Plan(), planProjectionValue); err != nil {
		t.Fatalf("declared source body refused: %v", err)
	}
	ordinary := map[string]any{"payload": raw}
	if err := value.ValidateProjected(ordinary, value.Plan(), planProjectionValue); !errors.Is(err, value.ErrLimit) {
		t.Fatalf("user snapshot key gained document text authority: %v", err)
	}
}

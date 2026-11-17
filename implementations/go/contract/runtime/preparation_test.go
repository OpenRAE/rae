package runtime_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)

func TestPreparationCommitmentsMatchPythonReference(t *testing.T) {
	var cases []struct {
		Name        string                     `json:"name"`
		Plan        binding.ProvisioningPlanV1 `json:"plan"`
		Snapshot    binding.RuntimeSnapshotV1  `json:"snapshot"`
		Request     string                     `json:"request_digest"`
		Predecessor string                     `json:"predecessor_digest"`
	}
	raw, err := os.ReadFile("testdata/preparation-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, c := range cases {
		t.Run(c.Name, func(t *testing.T) {
			result, err := runtimecontract.PrepareForRequest(c.Plan, c.Snapshot, nil, true, nil)
			if err != nil {
				t.Fatal(err)
			}
			if result.RequestDigest != c.Request || result.PredecessorDigest != c.Predecessor {
				t.Fatalf("commitments differ: %+v", result)
			}
		})
	}
}

type foreignPreparationValue struct{}

func (foreignPreparationValue) MarshalJSON() ([]byte, error) { panic("foreign callback invoked") }

func TestPreparationOwnsSelectedOperationsAndRejectsForeignValues(t *testing.T) {
	var fixture []struct {
		Plan     binding.ProvisioningPlanV1 `json:"plan"`
		Snapshot binding.RuntimeSnapshotV1  `json:"snapshot"`
	}
	raw, err := os.ReadFile("testdata/preparation-reference.json")
	if err != nil || json.Unmarshal(raw, &fixture) != nil || len(fixture) == 0 {
		t.Fatal("fixture", err)
	}
	plan, snapshot := fixture[0].Plan, fixture[0].Snapshot
	operations := []runtimecontract.ProvisionOperation{{Action: "create", Address: "provision.node.vm", ResourceType: "node", Payload: map[string]any{"nested": map[string]any{"value": "original"}}, OrderingDependencies: []string{"provision.node.base"}}}
	result, err := runtimecontract.PrepareForRequest(plan, snapshot, operations, true, nil)
	if err != nil {
		t.Fatal(err)
	}
	nested, ok := operations[0].Payload["nested"].(map[string]any)
	if !ok {
		t.Fatal("nested payload")
	}
	nested["value"] = "changed"
	operations[0].OrderingDependencies[0] = "changed"
	retained, ok := result.Operations[0].Payload["nested"].(map[string]any)
	if !ok {
		t.Fatal("retained payload")
	}
	if retained["value"] != "original" || result.Operations[0].OrderingDependencies[0] != "provision.node.base" {
		t.Fatal("selected operation alias retained")
	}
	operations[0].Payload = map[string]any{"foreign": foreignPreparationValue{}}
	if _, err := runtimecontract.PrepareForRequest(plan, snapshot, operations, true, nil); err == nil {
		t.Fatal("foreign value accepted")
	}
}

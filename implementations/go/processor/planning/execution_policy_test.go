package planning_test

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestPlanRetainsExecutionPolicyAndRefusesMissingSupport(t *testing.T) {
	compiled := compile(t, "name: example\nnodes:\n  server: {type: compute}\nexecution_policy:\n  default: {policy_id: stop, response: terminate}\n")
	unsupported, err := planning.PlanWithManifest(compiled, manifest(t), planning.Options{})
	if err != nil {
		t.Fatal(err)
	}
	if unsupported.Plan.Valid() || len(unsupported.Diagnostics) != 1 || unsupported.Diagnostics[0].Code != "execution-policy.response-unsupported" || len(field(unsupported.Plan.Provisioning().Diagnostics)) != 1 {
		t.Fatalf("policy refusal=%+v", unsupported.Diagnostics)
	}
	operations := field(unsupported.Plan.Provisioning().Operations)
	if len(operations) != 1 || len(field(operations[0].ExecutionPolicy)) == 0 {
		t.Fatal("effective execution policy was dropped")
	}
	target := changeManifest(t, func(record map[string]any) {
		record["execution_policy"] = map[string]any{"responses": []any{"terminate"}}
	})
	supported, err := planning.PlanWithManifest(compiled, target, planning.Options{})
	if err != nil || !supported.Plan.Valid() {
		t.Fatalf("supported policy refused: %+v %v", supported.Diagnostics, err)
	}
}

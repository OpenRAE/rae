package planning_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor/planning"
)

func TestPlanInjectBindingKeepsDefaultAndApplicationPoliciesAndEnforcesSupport(t *testing.T) {
	for _, explicit := range []bool{false, true} {
		t.Run(map[bool]string{false: "default", true: "application"}[explicit], func(t *testing.T) {
			checkPlannedBindingPolicy(t, explicit)
		})
	}
}

func checkPlannedBindingPolicy(t *testing.T, explicit bool) {
	t.Helper()
	raw, err := os.ReadFile("../testdata/node-binding-execution-policy.yaml")
	requireNoError(t, err)
	if explicit {
		raw = append(raw, []byte("  scopes:\n    - {scope: /nodes/host/injects/announce, policy: {policy_id: application, response: terminate}}\n")...)
	}
	compiled := compile(t, string(raw))
	target := changeManifest(t, func(record map[string]any) {
		record["execution_policy"] = map[string]any{"responses": []string{"terminate"}}
	})
	supported, err := planning.PlanWithManifest(compiled, target, planning.Options{})
	requireNoError(t, err)
	if !supported.Plan.Valid() {
		t.Fatalf("supported binding policy refused: %+v", supported.Diagnostics)
	}
	t.Run("projection", func(t *testing.T) {
		requirePlannedInjectPolicy(t, supported, explicit)
	})
	unsupported, err := planning.PlanWithManifest(compiled, manifest(t), planning.Options{})
	requireNoError(t, err)
	t.Run("unsupported", func(t *testing.T) {
		requireInjectPolicyRefusal(t, unsupported)
		requirePlannedInjectPolicy(t, unsupported, explicit)
	})
}

func requirePlannedInjectPolicy(t *testing.T, result planning.Result, explicit bool) {
	t.Helper()
	for _, operation := range field(result.Plan.Orchestration().Operations) {
		if field(operation.Address) != "orchestration.inject-binding.host.announce" {
			continue
		}
		var document map[string]any
		if len(field(operation.ExecutionPolicy)) == 0 {
			t.Fatal("planned inject binding execution policy omitted")
		}
		requireNoError(t, json.Unmarshal(field(operation.ExecutionPolicy), &document))
		id, response, scope, governing := "ambient", "terminate", "/injects/announce", "#/"
		if explicit {
			id, response, scope, governing = "application", "terminate", "/nodes/host/injects/announce", "#/nodes/host/injects/announce"
		}
		policy := requireType[map[string]any](t, document["policy"])
		if policy["policy_id"] != id || policy["response"] != response || document["scope"] != scope || document["governing_scope"] != governing {
			t.Fatalf("planned inject binding policy changed: %+v", document)
		}
		return
	}
	t.Fatal("planned inject binding missing")
}

func requireInjectPolicyRefusal(t *testing.T, result planning.Result) {
	t.Helper()
	for _, finding := range result.Diagnostics {
		if finding.Code == "execution-policy.response-unsupported" && finding.Domain == "orchestration" && finding.Address == "orchestration.inject-binding.host.announce" {
			if result.Plan.Valid() {
				t.Fatal("unsupported inject binding policy produced a valid plan")
			}
			return
		}
	}
	t.Fatalf("inject binding capability check omitted: %+v", result.Diagnostics)
}

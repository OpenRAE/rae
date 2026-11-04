package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestCleanupPlanAndIsolationRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"trial-cleanup-plan-references-and-retry-safe", `{"clean_state":{"mode":"fresh","boundary_refs":["b"],"verification_probe_refs":["probe"]},"resource_boundaries":{"b":{"boundary_id":"b","resource_refs":["resource"]}},"cleanup_obligations":{"o":{"obligation_id":"o","boundary_refs":["b"],"action_kind":"destroy","requirement":"required","verification_probe_refs":["probe"],"idempotency":"idempotent"}},"retry_policy":{"max_attempts":1,"after_effect_policy":"disallow"}}`, true},
		{"trial-cleanup-plan-references-and-retry-safe", `{"clean_state":{"mode":"fresh","boundary_refs":["missing"],"verification_probe_refs":["probe"]},"resource_boundaries":{},"cleanup_obligations":{},"retry_policy":{"max_attempts":1,"after_effect_policy":"disallow"}}`, false},
		{"trial-cleanup-plan-references-and-retry-safe", `{"clean_state":{"mode":"fresh","verification_probe_refs":["probe"]},"cleanup_obligations":{"a":{"obligation_id":"a","depends_on":["b"]},"b":{"obligation_id":"b","depends_on":["a"]}},"retry_policy":{"max_attempts":1,"after_effect_policy":"disallow"}}`, false},
		{"scheduler-isolation-serial-default-and-complete-parallel-proof", `{"plan_entry_ids":["e"]}`, true},
		{"scheduler-isolation-serial-default-and-complete-parallel-proof", `{"plan_entry_ids":["e"],"requested_parallelism":2}`, false},
		{"scheduler-isolation-serial-default-and-complete-parallel-proof", `{"plan_entry_ids":["e"],"requested_parallelism":1,"dimensions":[{"dimension":"storage","independent":true,"evidence_refs":["e"]}]}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

type testCleanupContext struct{ data []byte }

func (c testCleanupContext) CleanupPlan() []byte { return c.data }

func TestCleanupReceiptTrustedJoin(t *testing.T) {
	e := boundTestOwner(t)
	plan := fixtureObject(t, "fixtures/plans/trial-cleanup-plan-v1/valid/fresh-range.json")
	data, err := json.Marshal(plan)
	if err != nil {
		t.Fatal(err)
	}
	context := testCleanupContext{data: data}
	for _, name := range []string{"success", "required-cleanup-failed", "cancellation-cleanup-unverified", "timeout-cleanup-unsupported"} {
		receipt := fixtureObject(t, "fixtures/control-plane/trial-cleanup-receipt-v1/valid/"+name+".json")
		invocation := validation.Invocation{Instance: receipt, Root: receipt, Context: context}
		if err := validateTestDocument(t, e, "trial-cleanup-receipt-v1", invocation.Instance, invocation.Context); err != nil {
			t.Fatalf("receipt %s: %v", name, err)
		}
		invocation.Context = nil
		if err := validateTestDocument(t, e, "trial-cleanup-receipt-v1", invocation.Instance, invocation.Context); err == nil {
			t.Errorf("receipt %s accepted missing plan context", name)
		}
	}
	receipt := fixtureObject(t, "fixtures/control-plane/trial-cleanup-receipt-v1/valid/success.json")
	receipt["obligation_results"] = map[string]any{}
	if err := validateTestDocument(t, e, "trial-cleanup-receipt-v1", receipt, context); err == nil {
		t.Error("successful cleanup omitted an owed obligation")
	}
	receipt["cleanup_plan_ref"] = "other-plan"
	if err := validateTestDocument(t, e, "trial-cleanup-receipt-v1", receipt, context); err == nil {
		t.Error("receipt accepted another plan identity")
	}
}

func TestCleanupReceiptLocalModel(t *testing.T) {
	for _, test := range []struct {
		raw   string
		valid bool
	}{
		{`{"run_id":"r","execution_attempt_id":"a","cleanup_status":"succeeded","obligation_results":{"o":{"obligation_id":"o","status":"succeeded","evidence_refs":["verified"]}}}`, true},
		{`{"run_id":"r","execution_attempt_id":"r","cleanup_status":"succeeded"}`, false},
		{`{"run_id":"r","execution_attempt_id":"a","cleanup_status":"failed","clean_state_claim":{}}`, false},
		{`{"run_id":"r","execution_attempt_id":"a","cleanup_status":"succeeded","obligation_results":{"o":{"obligation_id":"o","status":"succeeded"}}}`, false},
	} {
		v := decodeRuleObject(t, test.raw)
		if err := cleanupReceiptLocal(v); (err == nil) != test.valid {
			t.Errorf("cleanupReceiptLocal(%s) = %v, want valid=%v", test.raw, err, test.valid)
		}
	}
}

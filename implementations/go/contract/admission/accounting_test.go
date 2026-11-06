package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestRunAccountingAndBatchReceipt(t *testing.T) {
	e := boundTestOwner(t)
	run := fixtureObject(t, "fixtures/experiment-core/experiment-run-v1/valid/reference.json")
	rule, ok := e.checker("run-execution-accounting-consistent")
	if !ok {
		t.Fatal("missing accounting rule")
	}
	if err := rule.check(validation.Invocation{Instance: run}); err != nil {
		t.Fatal(err)
	}
	run["record_state"] = "partial"
	if err := rule.check(validation.Invocation{Instance: run}); err == nil {
		t.Error("accepted partial record without attempt accounting")
	}
	rule, ok = e.checker("batch-execution-receipt-binds-plan-schedule-and-attempt")
	if !ok {
		t.Fatal("missing batch rule")
	}
	for _, name := range []string{"serial", "bounded-parallel"} {
		v := fixtureObject(t, "fixtures/control-plane/batch-execution-receipt-v1/valid/"+name+".json")
		if err := rule.check(validation.Invocation{Instance: v}); err != nil {
			t.Fatal(err)
		}
		v["execution_attempt_id"] = v["run_id"]
		if err := rule.check(validation.Invocation{Instance: v}); err == nil {
			t.Error("accepted attempt/run identity collision")
		}
	}
}

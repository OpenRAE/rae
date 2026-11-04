package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestArchivalRunRequiresEvidenceAndResults(t *testing.T) {
	for _, field := range []string{"evidence_artifacts", "result_summaries"} {
		run := decodeRuleObject(t, `{"run_status":"completed","execution_accounting":{},"ended_at":"2026-01-01T00:00:10Z","apparatus_context":{},"traceability":{},"evidence_artifacts":[{}],"result_summaries":{"result":{}}}`)
		if err := archivalRunShape(run); err != nil {
			t.Fatal(err)
		}
		object(run)[field] = nil
		if err := archivalRunShape(run); err == nil {
			t.Errorf("accepted archival run without %s", field)
		}
	}
}

func TestAccountingAttemptStartsAtRunStart(t *testing.T) {
	run := decodeRuleObject(t, `{"run_id":"r","run_status":"completed","started_at":"2026-01-01T00:00:00Z"}`)
	accounting := decodeRuleObject(t, `{"attempts":[{"execution_attempt_id":"a","attempt":1,"started_at":"2026-01-01T00:00:00Z","execution_status":"failed"},{"execution_attempt_id":"b","attempt":2,"started_at":"2026-01-01T00:00:01Z","execution_status":"succeeded"}]}`)
	if err := accountingAttempts(run, accounting, true); err != nil {
		t.Fatal(err)
	}
	first := object(array(at(accounting, "attempts"))[0])
	first["started_at"] = "2026-01-01T00:00:01Z"
	if err := accountingAttempts(run, accounting, true); err == nil {
		t.Error("accepted a first attempt starting after the run")
	}
}

func TestAccountingInvalidatedRunRetainsFailedAttempt(t *testing.T) {
	run := map[string]any{"run_status": "invalidated"}
	latest := map[string]any{"execution_status": "failed"}
	if err := accountingRunStatus(run, latest); err != nil {
		t.Fatalf("invalidated run lost retained attempt: %v", err)
	}
}

func TestParallelBatchRequiresLeaseEvidence(t *testing.T) {
	v := decodeRuleObject(t, `{"execution_attempt_id":"attempt","run_id":"run","plan_entry_id":"entry","plan_id":"plan","effective_parallelism":2,"isolation_proof_ref":"proof","lease_evidence_refs":["lease"]}`)
	if err := batchReceipt(validation.Invocation{Instance: v}); err != nil {
		t.Fatal(err)
	}
	object(v)["lease_evidence_refs"] = []any{}
	if err := batchReceipt(validation.Invocation{Instance: v}); err == nil {
		t.Error("accepted parallel execution without lease evidence")
	}
}

func TestAccountingRunEndCoversAttempt(t *testing.T) {
	run := decodeRuleObject(t, `{"ended_at":"2026-01-01T00:00:10Z"}`)
	attempt := decodeRuleObject(t, `{"started_at":"2026-01-01T00:00:00Z","ended_at":"2026-01-01T00:00:10Z","execution_status":"failed"}`)
	if err := accountingAttemptTime(attempt, run); err != nil {
		t.Fatal(err)
	}
	object(attempt)["ended_at"] = "2026-01-01T00:00:11Z"
	if err := accountingAttemptTime(attempt, run); err == nil {
		t.Error("accepted attempt beyond its run end")
	}
	delete(object(run), "ended_at")
	if err := accountingAttemptTime(attempt, run); err != nil {
		t.Fatalf("partial run cannot retain an observed attempt interval: %v", err)
	}
}

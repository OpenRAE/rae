package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/timestamp"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

const jsonOne json.Number = "1"

func (e *Validator) accountingRules() map[string]definition {
	return map[string]definition{
		"run-execution-accounting-consistent":                     {check: runAccounting},
		"batch-execution-receipt-binds-plan-schedule-and-attempt": {check: batchReceipt},
	}
}
func runAccounting(i validation.Invocation) error {
	v := i.Instance
	partial := stringAt(v, "record_state") == "partial"
	accounting := at(v, "execution_accounting")
	if partial {
		if accounting == nil || stringAt(v, "outcome_status") == outcomeSucceeded || stringAt(v, "run_status") == "sealed" {
			return invalid()
		}
	} else if err := archivalRunShape(v); err != nil {
		return err
	}
	unresolved := stringAt(v, "run_status") == statusInProgress || stringAt(v, "run_status") == outcomeIndeterminate
	if unresolved && at(v, "ended_at") != nil || at(v, "ended_at") == nil && (at(v, "difficulty_provenance") != nil || at(v, "realized_time_model") != nil) {
		return invalid()
	}
	if accounting == nil {
		return nil
	}
	return accountingAttempts(v, accounting, partial)
}
func archivalRunShape(v any) error {
	if stringAt(v, "run_status") == statusInProgress || stringAt(v, "run_status") == outcomeIndeterminate {
		return invalid()
	}
	if at(v, "execution_accounting") == nil && (len(array(at(v, "parameter_set"))) == 0 || len(array(at(v, "stochastic_controls"))) == 0) {
		return invalid()
	}
	return require(at(v, "ended_at") != nil && at(v, "apparatus_context") != nil && at(v, "traceability") != nil && len(array(at(v, "evidence_artifacts"))) > 0 && len(object(at(v, "result_summaries"))) > 0)
}
func accountingAttempts(run, accounting any, partial bool) error {
	attempts := array(at(accounting, "attempts"))
	if len(attempts) == 0 || len(rowSet(attempts, "execution_attempt_id")) != len(attempts) {
		return invalid()
	}
	start, err := timestamp.ParseRFC3339("started_at", stringAt(run, "started_at"))
	if err != nil {
		return invalid()
	}
	previous := start.Instant()
	for index, attempt := range attempts {
		if !countEqual(at(attempt, termAttempt), index+1) {
			return invalid()
		}
		if err := accountingAttempt(attempt, run, partial); err != nil {
			return err
		}
		instant, err := timestamp.ParseRFC3339("started_at", stringAt(attempt, "started_at"))
		if err != nil || instant.Instant().Before(previous) || index == 0 && !instant.Instant().Equal(previous) {
			return invalid()
		}
		previous = instant.Instant()
	}
	if err := accountingRunStatus(run, attempts[len(attempts)-1]); err != nil {
		return err
	}
	if !partial {
		return archivalAccounting(run, accounting, attempts)
	}
	return nil
}
func accountingAttempt(v, run any, partial bool) error {
	if err := accountingAttemptTime(v, run); err != nil {
		return err
	}
	if !fieldsUnique(v, "operation_refs") || len(rowTupleSet(at(v, "evidence_records"), "evidence_record_id", "record_version")) != len(array(at(v, "evidence_records"))) {
		return invalid()
	}
	for _, record := range array(at(v, "evidence_records")) {
		if !equal(at(record, "run_ref", fieldRefID), at(run, termRunID)) || stringAt(record, "run_ref", fieldRefKind) != kindRun {
			return invalid()
		}
	}
	cleanup := at(v, "cleanup_receipt")
	if cleanup != nil {
		if !equal(at(cleanup, "execution_attempt_id"), at(v, "execution_attempt_id")) || !equal(at(cleanup, termRunID), at(run, termRunID)) || !equal(at(cleanup, "cleanup_status"), defaultMember(v, "cleanup_status", "unobserved")) {
			return invalid()
		}
		return cleanupReceiptLocal(cleanup)
	}
	return require(partial)
}
func accountingRunStatus(v, latest any) error {
	expected := map[string]string{statusUnknown: outcomeIndeterminate, statusRunning: statusInProgress, outcomeSucceeded: "completed", outcomeFailed: outcomeFailed, "timed-out": outcomeFailed, outcomeCancelled: outcomeAborted, outcomeAborted: outcomeAborted}[stringAt(latest, "execution_status")]
	status := stringAt(v, "run_status")
	if status != expected && status != "invalidated" && status != statusSuperseded && (stringAt(latest, "execution_status") != outcomeSucceeded || status != "sealed") {
		return invalid()
	}
	return require((stringAt(latest, "execution_status") != statusUnknown && stringAt(latest, "execution_status") != statusRunning) || at(v, "ended_at") == nil)
}
func archivalAccounting(run, accounting any, attempts []any) error {
	linkage := at(run, "trial_provenance")
	if linkage == nil || !matchingFields(linkage, accounting, "plan_id", "plan_digest", "plan_entry_id", "entry_digest") || !equal(at(linkage, "terminal_attempt_id"), at(attempts[len(attempts)-1], "execution_attempt_id")) {
		return invalid()
	}
	linked := map[string]any{}
	for _, entry := range array(at(linkage, "execution_attempts")) {
		linked[stringAt(entry, "execution_attempt_id")] = entry
	}
	if len(linked) != len(attempts) {
		return invalid()
	}
	for _, attempt := range attempts {
		entry := linked[stringAt(attempt, "execution_attempt_id")]
		if !equal(at(entry, "cleanup_receipt_ref"), at(attempt, "cleanup_receipt", "receipt_id")) || !equalSet(set(at(entry, "operation_refs")), set(at(attempt, "operation_refs"))) {
			return invalid()
		}
	}
	return nil
}
func batchReceipt(i validation.Invocation) error {
	v := i.Instance
	attempt := stringAt(v, "execution_attempt_id")
	for _, field := range []string{termRunID, "plan_entry_id", "plan_id"} {
		if attempt == stringAt(v, field) {
			return invalid()
		}
	}
	if !fieldsUnique(v, "lease_evidence_refs", "operation_refs") {
		return invalid()
	}
	parallel := defaultMember(v, "effective_parallelism", jsonOne)
	if numericEqual(parallel, jsonOne) {
		return require(at(v, "isolation_proof_ref") == nil && len(array(at(v, "lease_evidence_refs"))) == 0)
	}
	return require(at(v, "isolation_proof_ref") != nil && len(array(at(v, "lease_evidence_refs"))) > 0)
}

func accountingAttemptTime(v, run any) error {
	start, err := timestamp.ParseRFC3339("started_at", stringAt(v, "started_at"))
	if err != nil {
		return invalid()
	}
	if at(v, "ended_at") != nil {
		end, err := timestamp.ParseRFC3339("ended_at", stringAt(v, "ended_at"))
		if err != nil || end.Instant().Before(start.Instant()) || stringAt(v, "execution_status") == statusUnknown || stringAt(v, "execution_status") == statusRunning {
			return invalid()
		}
		if at(run, "ended_at") != nil {
			runEnd, err := timestamp.ParseRFC3339("ended_at", stringAt(run, "ended_at"))
			if err != nil || end.Instant().After(runEnd.Instant()) {
				return invalid()
			}
		}
	}
	return nil
}

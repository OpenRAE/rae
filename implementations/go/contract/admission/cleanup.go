package admission

import (
	"math/big"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func (e *Validator) cleanupRules() map[string]definition {
	return map[string]definition{
		"trial-cleanup-plan-references-and-retry-safe":                   {check: cleanupPlan},
		"scheduler-isolation-serial-default-and-complete-parallel-proof": {check: isolationProof},
		"trial-cleanup-receipt-binds-plan-and-required-outcomes":         {check: e.cleanupReceipt, contextual: true, requiresContext: true},
	}
}
func cleanupPlan(i validation.Invocation) error {
	v := i.Instance
	boundaries, obligations := at(v, "resource_boundaries"), at(v, "cleanup_obligations")
	if !keyed(boundaries, "boundary_id") || !keyed(obligations, "obligation_id") {
		return invalid()
	}
	for _, boundary := range object(boundaries) {
		if !fieldsUnique(boundary, "resource_refs") {
			return invalid()
		}
	}
	if err := cleanStateRequirement(at(v, "clean_state")); err != nil {
		return err
	}
	if !subset(stringsOf(at(v, "clean_state", "boundary_refs")), keySet(boundaries)) {
		return invalid()
	}
	dependencies := map[string][]string{}
	for id, obligation := range object(obligations) {
		if err := cleanupObligation(obligation); err != nil {
			return err
		}
		if !subset(stringsOf(at(obligation, "boundary_refs")), keySet(boundaries)) || !subset(stringsOf(at(obligation, "depends_on")), keySet(obligations)) {
			return invalid()
		}
		dependencies[id] = stringsOf(at(obligation, "depends_on"))
	}
	if graph.HasCycle(dependencies) {
		return invalid()
	}
	return cleanupRetry(v)
}
func cleanStateRequirement(v any) error {
	if !fieldsUnique(v, "boundary_refs", "verification_probe_refs") {
		return invalid()
	}
	mode := stringAt(v, "mode")
	if (mode == "fresh" || mode == "verified-reset" || mode == "declared-reusable") && len(array(at(v, "verification_probe_refs"))) == 0 {
		return invalid()
	}
	return require((mode == "declared-reusable") == (at(v, "reusable_state_claim_ref") != nil))
}
func cleanupObligation(v any) error {
	if !fieldsUnique(v, "boundary_refs", "triggers", "depends_on", "compensation_refs", "verification_probe_refs") {
		return invalid()
	}
	if (stringAt(v, "action_kind") == "custom") != (at(v, "action_profile_ref") != nil) {
		return invalid()
	}
	if stringAt(v, "requirement") == requirementRequired && len(array(at(v, "verification_probe_refs"))) == 0 {
		return invalid()
	}
	return require(stringAt(v, "idempotency") != "requires-compensation" || len(array(at(v, "compensation_refs"))) > 0)
}
func cleanupRetry(v any) error {
	retry, obligations := at(v, "retry_policy"), at(v, "cleanup_obligations")
	if err := retryPolicy(retry); err != nil {
		return err
	}
	resetRefs := stringsOf(at(retry, "reset_obligation_refs"))
	if !subset(resetRefs, keySet(obligations)) {
		return invalid()
	}
	if stringAt(retry, "after_effect_policy") == retryReset {
		if err := resetCoverage(obligations, resetRefs); err != nil {
			return err
		}
	}
	attempts, ok := number(at(retry, termMaxAttempts))
	if !ok {
		return invalid()
	}
	if attempts.Cmp(big.NewRat(1, 1)) <= 0 {
		return nil
	}
	for _, obligation := range object(obligations) {
		posture := stringAt(retry, "after_effect_policy")
		if stringAt(obligation, "idempotency") != "idempotent" && posture != retryReset && posture != "compensate" {
			return invalid()
		}
	}
	return nil
}
func resetCoverage(obligations any, refs []string) error {
	reset := map[string]bool{}
	for _, ref := range refs {
		obligation := object(obligations)[ref]
		if stringAt(obligation, "action_kind") != retryReset || !set(at(obligation, "triggers"))[termRetry] || stringAt(obligation, "requirement") != requirementRequired {
			return invalid()
		}
		for _, boundary := range stringsOf(at(obligation, "boundary_refs")) {
			reset[boundary] = true
		}
	}
	for _, obligation := range object(obligations) {
		if stringAt(obligation, "idempotency") != "idempotent" && !subset(stringsOf(at(obligation, "boundary_refs")), reset) {
			return invalid()
		}
	}
	return nil
}
func isolationProof(i validation.Invocation) error {
	v := i.Instance
	if !fieldsUnique(v, "plan_entry_ids") || !unique(rowIDs(at(v, "dimensions"), "dimension")) {
		return invalid()
	}
	parallel, ok := defaultNumber(v, "requested_parallelism", 1)
	if !ok {
		return invalid()
	}
	if parallel.Cmp(big.NewRat(1, 1)) <= 0 {
		return require(len(array(at(v, "dimensions"))) == 0)
	}
	if parallel.Cmp(big.NewRat(int64(len(array(at(v, "plan_entry_ids")))), 1)) > 0 {
		return invalid()
	}
	independent := map[string]bool{}
	for _, dimension := range array(at(v, "dimensions")) {
		if !fieldsUnique(dimension, fieldEvidenceRefs) || !boolean(at(dimension, termIndependent)) {
			return invalid()
		}
		independent[stringAt(dimension, "dimension")] = true
	}
	return require(subset([]string{"range-instance", "host-capacity", "ports", "storage", "control-plane-locks", "secret-scope", termCleanup}, independent))
}

func cleanupReceiptLocal(v any) error {
	if equal(at(v, "execution_attempt_id"), at(v, termRunID)) || !keyed(at(v, "obligation_results"), "obligation_id") {
		return invalid()
	}
	status := stringAt(v, "cleanup_status")
	if status == "not-required" && len(object(at(v, "obligation_results"))) > 0 {
		return invalid()
	}
	if at(v, "clean_state_claim") != nil && status != outcomeSucceeded {
		return invalid()
	}
	if !fieldsUnique(at(v, "clean_state_claim"), "boundary_refs", fieldEvidenceRefs) {
		return invalid()
	}
	for _, result := range object(at(v, "obligation_results")) {
		if err := cleanupResult(result); err != nil {
			return err
		}
		if status == outcomeSucceeded && stringAt(result, "status") != outcomeSucceeded && stringAt(result, "status") != resultNotTriggered {
			return invalid()
		}
	}
	return nil
}
func cleanupResult(v any) error {
	if !fieldsUnique(v, fieldEvidenceRefs, "residual_state_refs") {
		return invalid()
	}
	status := stringAt(v, "status")
	if status == outcomeSucceeded {
		return require(len(array(at(v, fieldEvidenceRefs))) > 0 && len(array(at(v, "residual_state_refs"))) == 0)
	}
	return require((status != outcomeFailed && status != "unverified") || len(array(at(v, fieldEvidenceRefs)))+len(array(at(v, "residual_state_refs"))) > 0)
}
func (e *Validator) cleanupReceipt(i validation.Invocation) error {
	if err := cleanupReceiptLocal(i.Instance); err != nil {
		return err
	}
	context, ok := i.Context.(CleanupContext)
	if !ok {
		return contextRequired()
	}
	plan, err := e.contextDocument(termTrialCleanupPlanV1, context.CleanupPlan())
	if err != nil {
		return err
	}
	return cleanupReceiptJoin(plan, i.Instance)
}
func cleanupReceiptJoin(plan, receipt any) error {
	if !equal(at(receipt, "cleanup_plan_ref"), at(plan, "plan_id")) || !equal(at(receipt, "plan_entry_id"), at(plan, "plan_entry_id")) || !equal(at(receipt, termRunID), at(plan, termRunID)) {
		return invalid()
	}
	obligations := at(plan, "cleanup_obligations")
	if !subset(mapKeys(at(receipt, "obligation_results")), keySet(obligations)) || !subset(stringsOf(at(receipt, "clean_state_claim", "boundary_refs")), keySet(at(plan, "resource_boundaries"))) {
		return invalid()
	}
	trigger := map[string]string{outcomeSucceeded: outcomeSuccess, outcomeFailed: outcomeFailure, outcomeCancelled: termCancellation, "timed-out": "timeout", outcomeAborted: "abort"}[stringAt(receipt, "trial_outcome")]
	for id, obligation := range object(obligations) {
		result := at(receipt, "obligation_results", id)
		triggered := set(at(obligation, "triggers"))[trigger]
		if err := owedCleanupResult(obligation, result, triggered, stringAt(receipt, "cleanup_status")); err != nil {
			return err
		}
		if result != nil && triggered == (stringAt(result, "status") == resultNotTriggered) {
			return invalid()
		}
	}
	return nil
}
func owedCleanupResult(obligation, result any, triggered bool, status string) error {
	if stringAt(obligation, "requirement") != requirementRequired || !triggered {
		return nil
	}
	if result == nil || stringAt(result, "status") == "skipped" || stringAt(result, "status") == resultNotTriggered {
		return invalid()
	}
	return require(status != outcomeSucceeded || stringAt(result, "status") == outcomeSucceeded)
}
func mapKeys(v any) []string {
	keys := make([]string, 0, len(object(v)))
	for key := range object(v) {
		keys = append(keys, key)
	}
	return keys
}

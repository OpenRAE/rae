package stub

import (
	"encoding/json"
	"math/big"
)

func evaluationState(operation map[string]any, now string) (map[string]any, []map[string]any) {
	contract := object(object(operation, "payload"), "result_contract")
	schema := contract[termStateSchemaVersion]
	if schema == nil {
		schema = "evaluation-result-state/v1"
	}
	kind := contract["resource_type"]
	if kind == nil {
		kind = operation["resource_type"]
	}
	result := map[string]any{termStateSchemaVersion: schema, "resource_type": kind, "run_id": "evaluation-run", termStatus: termReady, "observed_at": now, termUpdatedAt: now, termDetail: "stub result for " + text(operation, "address"), termEvidenceRefs: []any{}}
	if resultCapability(contract["supports_score"]) {
		score := contract["fixed_max_score"]
		if score == nil {
			score = 100
		}
		result["score"] = score
		result["max_score"] = score
	}
	if resultCapability(contract["supports_passed"]) {
		result["passed"] = true
	}
	history := []map[string]any{
		{termEventType: "evaluation_started", termTimestamp: now, termStatus: termRunning, "passed": nil, "score": nil, "max_score": nil, termDetail: nil, termEvidenceRefs: []any{}, termDetails: map[string]any{}},
		{termEventType: "evaluation_ready", termTimestamp: now, termStatus: termReady, "passed": result["passed"], "score": result["score"], "max_score": result["max_score"], termDetail: result[termDetail], termEvidenceRefs: result[termEvidenceRefs], termDetails: map[string]any{}},
	}
	return result, history
}

// Contract payload flags follow the reference's JSON truth-value semantics.
func resultCapability(input any) bool {
	switch value := input.(type) {
	case nil:
		return false
	case bool:
		return value
	case string:
		return value != ""
	case json.Number:
		number, ok := new(big.Rat).SetString(value.String())
		return ok && number.Sign() != 0
	case []any:
		return len(value) > 0
	case map[string]any:
		return len(value) > 0
	default:
		return false
	}
}

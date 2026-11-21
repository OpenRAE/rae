package stub

import (
	"encoding/json"
	"maps"
	"slices"
)

// Participant behavior history uses exclude_none/exclude_defaults, recursively
// through typed models. Extension dictionaries remain opaque. These omissions
// follow contracts/participant_runtime.py, participant_temporal.py and time_model.py.
func participantModelPayload(model string, input map[string]any) map[string]any {
	result := maps.Clone(input)
	for key, value := range result {
		if value == nil || participantDefault(model, key, value) {
			delete(result, key)
			continue
		}
		child := participantChildModel(model, key)
		if child == "" {
			continue
		}
		result[key] = participantChildPayload(child, value)
	}
	return result
}

func participantChildPayload(model string, input any) any {
	switch value := input.(type) {
	case map[string]any:
		return participantModelPayload(model, value)
	case []any:
		result := make([]any, len(value))
		for i, item := range value {
			result[i] = participantChildPayload(model, item)
		}
		return result
	default:
		return input
	}
}

func participantDefault(model, key string, input any) bool {
	emptyLists := map[string][]string{
		"action":       {"preconditions", "effects", "observations", "resource_measurements", "temporal_evidence", termEvidenceRefs, termDiagnostics},
		"precondition": {"support_refs", termEvidenceRefs, termDiagnostics},
		"effect":       {"target_refs", termEvidenceRefs, termDiagnostics},
		"temporal":     {"backend_disclosure_refs"},
		termProof:      {termCoverage},
		termBinding:    {"backend_disclosure_refs"},
	}
	if values, ok := input.([]any); ok && len(values) == 0 && slices.Contains(emptyLists[model], key) {
		return true
	}
	if model == termProof && key == "evidence_mode" && input == "event" {
		return true
	}
	if model == termBinding && key == "profile" && input == "participant-shared-time/v1" {
		return true
	}
	return model == termCoordinate && (key == "segment" || key == "microstep") && input == json.Number("0")
}

func participantChildModel(model, key string) string {
	children := map[string]map[string]string{
		"action":     {"preconditions": "precondition", "effects": "effect", "temporal_evidence": termProof},
		"temporal":   {"shared_time": termContext},
		termProof:    {termContext: termContext, termCoordinate: termCoordinate, termCoverage: termCoverage},
		termContext:  {termBinding: termBinding, "submitted_at": termCoordinate, "bound_start": termCoordinate, "bound_end": termCoordinate},
		termBinding:  {"start": termCoordinate, "end": termCoordinate},
		termCoverage: {"start": termCoordinate, "end": termCoordinate},
	}
	return children[model][key]
}

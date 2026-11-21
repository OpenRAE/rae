package stub

import (
	"encoding/json"
	"testing"
)

func TestParticipantEventPayloadOmitsOnlyModelDefaults(t *testing.T) {
	input := map[string]any{"status": "succeeded", "preconditions": []any{}, "failure_class": nil, "resource_measurements": []any{map[string]any{"measured": json.Number("0"), "resource_kind": map[string]any{"coordinate": "urn:resource", "parameters": map[string]any{"empty": []any{}, "none": nil}}, "evidence_refs": []any{"evidence"}}}, "temporal_evidence": []any{map[string]any{"evidence_mode": "event", "coverage": []any{}, "context": map[string]any{"clock_sequence": json.Number("0"), "bound_end": map[string]any{"segment": json.Number("0"), "tick": json.Number("0"), "microstep": json.Number("0")}}}}}
	result := participantModelPayload("action", input)
	if _, present := result["preconditions"]; present {
		t.Fatal("default list retained")
	}
	if _, present := result["failure_class"]; present {
		t.Fatal("None retained")
	}
	proofs := array(result["temporal_evidence"])
	first, ok := proofs[0].(map[string]any)
	if !ok {
		t.Fatal("proof")
	}
	if _, present := first["evidence_mode"]; present {
		t.Fatal("default evidence mode retained")
	}
	context := object(first, "context")
	coordinate := object(context, "bound_end")
	if _, present := coordinate["tick"]; !present {
		t.Fatal("required zero tick lost")
	}
	if _, present := coordinate["segment"]; present {
		t.Fatal("default coordinate retained")
	}
	if _, present := context["clock_sequence"]; !present {
		t.Fatal("required zero sequence lost")
	}
	measurements := array(result["resource_measurements"])
	measurement, ok := measurements[0].(map[string]any)
	if !ok {
		t.Fatal("measurement")
	}
	parameters := object(object(measurement, "resource_kind"), "parameters")
	if _, present := parameters["empty"]; !present {
		t.Fatal("extension data changed")
	}
	if _, present := input["failure_class"]; !present {
		t.Fatal("input mutated")
	}
}

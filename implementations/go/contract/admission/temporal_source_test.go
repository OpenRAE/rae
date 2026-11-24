package admission

import "testing"

func TestSharedTimeSourceBindings(t *testing.T) {
	valid := `{"clocks":{"clock":{"time_domain_ref":"domain"}},"time_domains":{"domain":{"kind":"logical"}},"temporal_constraints":{"limit":{"clock_ref":"clock","constraint_kind":"deadline","subject_refs":["action_contracts.action"]}},"action_contracts":{"action":{"temporal_contracts":[{"temporal_kind":"deadline","time_domain":"scenario_time","shared_time_binding":{"clock_ref":"clocks.clock","constraint_ref":"limit"}}]}}}`
	assertRule(t, "participant-shared-time-source-bindings", valid, true)
	v := decodeRuleObject(t, valid)
	object(at(v, "temporal_constraints", "limit"))["clock_ref"] = "other"
	assertObjectRule(t, "participant-shared-time-source-bindings", v, false)
	object(at(v, "temporal_constraints", "limit"))["clock_ref"] = "clock"
	object(at(v, "temporal_constraints", "limit"))["subject_refs"] = []any{"other-action"}
	assertObjectRule(t, "participant-shared-time-source-bindings", v, false)
}

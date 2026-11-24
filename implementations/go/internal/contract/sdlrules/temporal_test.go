package sdlrules

import (
	"slices"
	"testing"
)

func TestTemporalProjectionRefusesMalformedTypedFields(t *testing.T) {
	for _, raw := range []string{`{`, `[]`, `{"action_contracts":{"a":{"temporal_contracts":[{"shared_time_binding":{"clock_ref":[]}}]}}}`, `{"temporal_constraints":{"c":{"start":{"tick":[]}}}}`, `{"behavior_specifications":{"s":{"autonomous_execution":{"action_candidates":[]}}}}`} {
		if findings, err := TemporalBindings([]byte(raw), nil); err == nil || len(findings) != 0 {
			t.Errorf("malformed projection produced findings %v, error %v", findings, err)
		}
	}
}
func TestTemporalBindingsKeepCallerDataAndOrder(t *testing.T) {
	raw := []byte(`{"action_contracts":{"a":{"temporal_contracts":[{"shared_time_binding":{"clock_ref":"missing","constraint_ref":"missing"}}]},"b":{"temporal_contracts":[{"shared_time_binding":{"clock_ref":"missing","constraint_ref":"missing"}}]}}}`)
	before := string(raw)
	order := map[string][]string{"/action_contracts": {"b", "a"}}
	findings, err := TemporalBindings(raw, order)
	if err != nil || len(findings) != 4 {
		t.Fatalf("findings=%v, error=%v", findings, err)
	}
	if findings[0].Owner.Name != "b" || findings[2].Owner.Name != "a" {
		t.Fatalf("reporter changed authored order: %v", findings)
	}
	if string(raw) != before || !slices.Equal(order["/action_contracts"], []string{"b", "a"}) {
		t.Fatal("reporter changed caller data or order")
	}
}

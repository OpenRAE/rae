package admission

import "testing"

func TestSelectionRegistryRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"experiment-selection-policies-valid", `{"target_run_count":1,"selection_policies":{"a":{"policy_id":"a","kind":"fixed","output_bound":1}}}`, true},
		{"experiment-selection-policies-valid", `{"target_run_count":1,"selection_policies":{"a":{"policy_id":"a","kind":"fixed","output_bound":2}}}`, false},
		{"experiment-selection-policies-valid", `{"target_run_count":2,"selection_policies":{"a":{"policy_id":"a","kind":"product","policy_refs":["b","c"],"purpose":"nuisance-variation","output_bound":1},"b":{"policy_id":"b","kind":"fixed","output_bound":1},"c":{"policy_id":"c","kind":"fixed","output_bound":1}}}`, true},
		{"experiment-selection-policies-valid", `{"target_run_count":2,"selection_policies":{"a":{"policy_id":"a","kind":"product","policy_refs":["a","a"],"output_bound":1}}}`, false},
		{"experiment-selection-policies-valid", `{"target_run_count":2,"selection_policies":{"a":{"policy_id":"a","kind":"sample","sample_count":2,"output_bound":2,"stochastic_control_ref":"s"}},"stochastic_controls":[{"control_id":"s","role":"sampling","executable_binding":{"profile_ref":{"ref_id":"blake3-xof-v1"}}}]}`, true},
		{"experiment-selection-policies-valid", `{"target_run_count":2,"selection_policies":{"a":{"policy_id":"a","kind":"sample","sample_count":2,"output_bound":2,"stochastic_control_ref":"s"}},"stochastic_controls":[{"control_id":"s","role":"sampling"}]}`, false},
		{"experiment-selection-factor-joins-valid", `{"run_plan":{"selection_policies":{"a":{"binding_descriptor_refs":["b"],"point_ref":"v"}}},"binding_descriptors":{"descriptors":[{"binding_id":"b","target":{"variation_point_id":"v"}}]}}`, true},
		{"experiment-selection-factor-joins-valid", `{"run_plan":{"selection_policies":{"a":{"binding_descriptor_refs":["b"],"point_ref":"other"}}},"binding_descriptors":{"descriptors":[{"binding_id":"b","target":{"variation_point_id":"v"}}]}}`, false},
		{"stochastic-draws-control-ref-resolves", `{"stochastic_controls":[{"control_id":"s","executable_binding":{"profile_ref":{"ref_id":"blake3-xof-v1"},"namespace":"n"}}],"stochastic_draws":[{"control_id":"s","address":{"namespace":"n"},"transform_id":"bounded-integer","transform_version":"1"}]}`, true},
		{"stochastic-draws-control-ref-resolves", `{"stochastic_controls":[{"control_id":"s","executable_binding":{"profile_ref":{"ref_id":"blake3-xof-v1"},"namespace":"n"}}],"stochastic_draws":[{"control_id":"s","address":{"namespace":"other"},"transform_id":"bounded-integer","transform_version":"1"}]}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

package admission

import "testing"

func TestAllocationJoins(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"run-allocation-condition-assignments-valid", `{"compared_conditions":["a","b"],"condition_assignments":{"a":{"condition_id":"a","factor_levels":{"f":"one"},"required_parameters":[{"name":"p","value_kind":"configuration","value":1}]},"b":{"condition_id":"b","factor_levels":{"f":"two"},"required_parameters":[{"name":"p","value_kind":"configuration","value":2}]}}}`, true},
		{"run-allocation-condition-assignments-valid", `{"compared_conditions":["a","b"],"condition_assignments":{"a":{"condition_id":"a","factor_levels":{"f":"one"},"required_refs":[{"ref_id":"same"}]},"b":{"condition_id":"b","factor_levels":{"f":"two"},"required_refs":[{"ref_id":"same"}]}}}`, false},
		{"run-allocation-condition-assignments-valid", `{"compared_conditions":["a","b"],"condition_assignments":{"a":{"condition_id":"a","factor_levels":{"f":"one"},"required_refs":[{"ref_id":"one"}]},"b":{"condition_id":"b","factor_levels":{"f":"one"},"required_refs":[{"ref_id":"two"}]}}}`, false},
		{"run-allocation-condition-assignments-valid", `{"compared_conditions":["a"],"condition_assignments":{"a":{"condition_id":"other","factor_levels":{"f":"one"},"required_refs":[{}]}}}`, false},
		{"experiment-binding-source-joins-valid", `{"binding_semantics":"descriptive"}`, true},
		{"experiment-binding-source-joins-valid", `{"binding_semantics":"explicit-required"}`, false},
		{"experiment-binding-source-joins-valid", `{"binding_semantics":"explicit-required","factors":{"f":{"levels":["l"]}},"run_plan":{"allocation":{"compared_conditions":["c"],"condition_assignments":{"c":{"factor_levels":{"f":"l"}}}}},"binding_descriptors":{"descriptors":[{"source_condition_id":"c","source_factor_id":"f","source_factor_level_id":"l"}]}}`, true},
		{"experiment-binding-source-joins-valid", `{"binding_semantics":"explicit-required","factors":{"f":{"levels":["l"]}},"run_plan":{"allocation":{"compared_conditions":["c"],"condition_assignments":{"c":{"factor_levels":{"f":"other"}}}}},"binding_descriptors":{"descriptors":[{"source_condition_id":"c","source_factor_id":"f","source_factor_level_id":"l"}]}}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
}

package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
)

func TestPlanningLocalRules(t *testing.T) {
	for _, test := range []struct {
		id, raw string
		valid   bool
	}{
		{"run-plan-exactly-one-run-count-source", `{"target_run_count":1}`, true},
		{"run-plan-exactly-one-run-count-source", `{"target_run_count":1,"allocation":{}}`, false},
		{"run-plan-exactly-one-run-count-source", `{"target_run_count":1,"red_variant_selections":{"a":{"variant_id":"b"}}}`, false},
		{"experiment-spec-blocking-factors-declared", `{"factors":{"b":{}},"run_plan":{"allocation":{"blocking_factors":["b"]}}}`, true},
		{"experiment-spec-blocking-factors-declared", `{"run_plan":{"allocation":{"blocking_factors":["b"]}}}`, false},
		{"experiment-spec-condition-factor-levels-declared", `{"factors":{"f":{"levels":["a"]}},"run_plan":{"allocation":{"condition_assignments":{"c":{"factor_levels":{"f":"a"}}}}}}`, true},
		{"experiment-spec-condition-factor-levels-declared", `{"factors":{"f":{"levels":["a"]}},"run_plan":{"allocation":{"condition_assignments":{"c":{"factor_levels":{"f":"b"}}}}}}`, false},
		{"binding-descriptors-canonical-targets-injective", `{"descriptors":[{"binding_id":"a","source_condition_id":"c","target":{"plane":"scenario","scenario_family_id":"f","variation_point_id":"v","target_id":"t"}},{"binding_id":"b","source_condition_id":"d","target":{"plane":"scenario","scenario_family_id":"f","variation_point_id":"v","target_id":"t"}}]}`, true},
		{"binding-descriptors-canonical-targets-injective", `{"descriptors":[{"binding_id":"a","source_condition_id":"c","target":{"plane":"scenario","scenario_family_id":"f","variation_point_id":"v","target_id":"t"}},{"binding_id":"b","source_condition_id":"c","target":{"plane":"scenario","scenario_family_id":"f","variation_point_id":"v","target_id":"t"}}]}`, false},
		{"claim-bearing-study-analysis-plan-required", `{"study_kind":"collection"}`, true},
		{"claim-bearing-study-analysis-plan-required", `{"study_kind":"study"}`, false},
		{"adaptive-difficulty-study-validity-treatment-required", `{"run_allocation":{"condition_assignments":{"c":{"difficulty_condition":"adaptive"}}},"analysis_plan":{},"validity_notes":[{}]}`, true},
		{"adaptive-difficulty-study-validity-treatment-required", `{"run_allocation":{"condition_assignments":{"c":{"difficulty_condition":"scaffolded"}}}}`, false},
		{"difficulty-policy-registry-valid", `{"allocation":{"condition_assignments":{"c":{"difficulty_condition":"fixed"}}}}`, true},
		{"difficulty-policy-registry-valid", `{"allocation":{"condition_assignments":{"c":{"difficulty_condition":"adaptive"}}}}`, false},
		{"difficulty-policy-registry-valid", `{"difficulty_policy_registry":{"default_policy_id":"p","policies":{"p":{"condition":"adaptive"}},"variants":{"v":{"selection_policy_refs":["s"]}}},"selection_policies":{"s":{"kind":"fixed"}},"allocation":{"condition_assignments":{"c":{"difficulty_condition":"adaptive"}}}}`, true},
		{"difficulty-policy-registry-valid", `{"difficulty_policy_registry":{"default_policy_id":"p","policies":{"p":{"condition":"adaptive"}},"variants":{"v":{"selection_policy_refs":["s"]}}},"selection_policies":{"s":{"kind":"uniform"}}}`, false},
	} {
		assertRule(t, test.id, test.raw, test.valid)
	}
	v := map[string]any{"source_condition_id": "c", "source_factor_id": "f", "target": map[string]any{"plane": "scenario", "scenario_family_id": "family", "variation_point_id": "point", "target_id": "target"}, "selection_id": "selection-" + digest.SHA256([]byte(`["c","f",["scenario","family","point","target"]]`))[7:]}
	raw, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	assertRule(t, "experiment-selection-treatment-identity-valid", string(raw), true)
	v["source_factor_id"] = "other"
	raw, err = json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	assertRule(t, "experiment-selection-treatment-identity-valid", string(raw), false)
}

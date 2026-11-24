package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func TestAuthoringRules(t *testing.T) {
	for _, test := range []struct {
		raw   string
		valid bool
	}{
		{`{"left":null,"right":null,"artifact_relation":"incomparable","diagnostic_relation":"incomparable","provenance_relation":"incomparable","semantic_relation":"incomparable"}`, true},
		{`{"left":null,"right":null,"left_matches_expected":true,"artifact_relation":"incomparable","diagnostic_relation":"incomparable","provenance_relation":"incomparable","semantic_relation":"incomparable"}`, false},
		{`{"left":{"outcome":"refused"},"right":{"outcome":"refused"},"artifact_relation":"not-applicable","diagnostic_relation":"equivalent","provenance_relation":"not-applicable","semantic_relation":"not-applicable"}`, true},
		{`{"left":{"outcome":"success","artifact_coordinate":{},"canonical_artifact_digest":"sha256:artifact"},"right":{"outcome":"success","artifact_coordinate":{},"canonical_artifact_digest":"sha256:artifact"},"artifact_relation":"equivalent","diagnostic_relation":"equivalent","provenance_relation":"not-applicable","semantic_relation":"equivalent"}`, false},
		{`{"left":{"outcome":"success","artifact_coordinate":{},"canonical_artifact_digest":"sha256:artifact"},"right":{"outcome":"success","artifact_coordinate":{},"canonical_artifact_digest":"sha256:artifact"},"artifact_relation":"equivalent","diagnostic_relation":"equivalent","provenance_relation":"not-applicable","semantic_relation":"equivalent","semantic_result_digest":"sha256:x"}`, true},
	} {
		assertRule(t, "authoring-comparison-evidence-shape", test.raw, test.valid)
	}
	operation := map[string]any{"profile": "validate-sdl/v1"}
	v := map[string]any{"input_source": "source\n", "input_digest": digest.SHA256([]byte("source\n")), "operation": operation, "operation_digest": digest.SHA256([]byte(`{"new_local_name":null,"profile":"validate-sdl/v1","target_address":null}`)), "expected": map[string]any{"outcome": "refused"}}
	raw, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	assertRule(t, "authoring-vector-bound-inputs", string(raw), true)
	v["input_source"] = "source"
	raw, err = json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	assertRule(t, "authoring-vector-bound-inputs", string(raw), false)
}

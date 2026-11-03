package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestSynthesisRulesUseCompleteDefaultsAndJoins(t *testing.T) {
	e := boundTestOwner(t)
	check := func(id string, value any, valid bool) {
		t.Helper()
		rule, ok := e.checker(id)
		if !ok {
			t.Fatalf("missing rule %s", id)
		}
		if err := rule.check(validation.Invocation{Instance: value, Root: value}); (err == nil) != valid {
			t.Errorf("%s() = %v, want valid=%v", id, err, valid)
		}
	}
	input := fixtureObject(t, "fixtures/candidate-synthesis/sdl-candidate-synthesis-input-v1/valid/attack-enterprise.json")
	check("candidate-synthesis-pinned-source-join", input, true)
	check("candidate-synthesis-stable-input-order", input, true)
	object(input["source"])["revision"] = "other-revision"
	check("candidate-synthesis-pinned-source-join", input, false)
	profile := fixtureObject(t, "profiles/candidate-synthesis/concept-nodes-v1.json")
	check("candidate-synthesis-complete-profile-digest", profile, true)
	delete(profile, "limits")
	delete(profile, "default_ids")
	check("candidate-synthesis-complete-profile-digest", profile, true)
	profile["rule_ids"] = []any{"other-rule"}
	check("candidate-synthesis-complete-profile-digest", profile, false)
	record := fixtureObject(t, "fixtures/candidate-synthesis/sdl-candidate-synthesis-record-v1/valid/attack-enterprise.json")
	check("candidate-synthesis-all-or-none", record, true)
	check("candidate-synthesis-provenance-separation", record, true)
	traces := array(record["construct_traces"])
	object(traces[0])["contributions"] = []any{map[string]any{"kind": "inferred-structure", "ref_id": "concept-node-emission"}}
	check("candidate-synthesis-provenance-separation", record, false)
	record["candidate_canonical_digest"] = nil
	check("candidate-synthesis-all-or-none", record, false)
}

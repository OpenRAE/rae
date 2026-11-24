package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestDecisionSurfaceExposureAndPlanes(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct{ id, rule, name string }{
		{"participant-decision-surface-v1", "decision-surface-entry-reference-agreement", "human-candidate"},
		{"participant-decision-surface-v2", "decision-surface-v2-plane-separation", "delivered-initial"},
	} {
		v := fixtureObject(t, "fixtures/control-plane/"+test.id+"/valid/"+test.name+".json")
		rule, ok := e.checker(test.rule)
		if !ok {
			t.Error("missing rule", test.rule)
			continue
		}
		if err := rule.check(validation.Invocation{Root: v, Instance: v}); err != nil {
			t.Errorf("%s: %v", test.id, err)
		}
		if test.id == "participant-decision-surface-v2" {
			object(v["delivery"])["participant_view_digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		} else {
			object(array(v["exposure_bindings"])[0])["participant_address"] = "different"
		}
		if err := rule.check(validation.Invocation{Root: v, Instance: v}); err == nil {
			t.Error("accepted mismatched exposure or delivery")
		}
	}
	for _, raw := range []string{
		`{"visible_context_refs":["context"],"action_entries":[{"entry_id":"action","action_contract_address":"address","selection_shape_ref":"shape","eligibility":"eligible","support":"unsupported","constraint_refs":["constraint"]}],"form":{"surface_form":"candidate_action_set","candidate_entry_ids":["missing"]}}`,
		`{"visible_context_refs":["context"],"action_entries":[{"entry_id":"action","action_contract_address":"address","selection_shape_ref":"shape","eligibility":"eligible","support":"unsupported","constraint_refs":["constraint"]}],"form":{"surface_form":"constrained_form","action_entry_id":"action","argument_shape_ref":"wrong"}}`,
	} {
		if err := decisionView(decodeRuleObject(t, raw)); err == nil {
			t.Error("accepted unresolved surface reference")
		}
	}
}

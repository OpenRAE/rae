package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type controlHistoryTestContext struct {
	records, policies [][]byte
	available         []AvailableControlTarget
	declarations      []ControlDeclaration
	targets           []ControlTarget
}

func (c controlHistoryTestContext) ControlOccurrences() [][]byte              { return c.records }
func (c controlHistoryTestContext) ControlDeclarations() []ControlDeclaration { return c.declarations }
func (c controlHistoryTestContext) ControlTargets() []ControlTarget           { return c.targets }

func (c controlHistoryTestContext) ControlOccurrencePolicies() [][]byte { return c.policies }
func (c controlHistoryTestContext) ControlAvailableTargets() []AvailableControlTarget {
	return c.available
}

func handoffPolicy(record any) map[string]any {
	v := at(record, "occurrence")
	state := func(id any, controller any) any {
		return map[string]any{"state_ref": id, "controller_ref": controller, "authority_basis_refs": at(v, "authority_basis_refs"), "scope_refs": at(v, "controlled_scope_refs"), "authority_status": "active", "valid_from_order": at(v, "valid_from_order"), "valid_until_order": at(v, "valid_until_order")}
	}
	return map[string]any{"semantics": at(record, "semantics"), "participant_address": at(record, "participant_address"), "episode_id": at(record, "episode_id"), "pin": at(record, "policy"), "order_strategy": "total-effective-order", "initial_state_ref": at(v, "prior_state_ref"), "behavior_scope_refs": at(v, "controlled_scope_refs"), "states": []any{state(at(v, "prior_state_ref"), at(v, "controller_ref")), state(at(v, "resulting_state_ref"), "controller.supervised")}, "transitions": []any{map[string]any{"transition_ref": at(v, "permitted_transition_ref"), "kind": "handoff", "from_state_ref": at(v, "prior_state_ref"), "to_state_ref": at(v, "resulting_state_ref"), "valid_from_order": at(v, "valid_from_order"), "valid_until_order": at(v, "valid_until_order"), "target_kinds": []any{}}}, "script_steps": []any{}}
}

func TestControlV2FoldsAcceptedAndRejectedHistory(t *testing.T) {
	e := boundTestOwner(t)
	accepted := fixtureObject(t, "fixtures/participant-runtime/participant-control-occurrence-v2/valid/accepted-handoff.json")
	rejected := fixtureObject(t, "fixtures/participant-runtime/participant-control-occurrence-v2/valid/rejected-stale-state.json")
	policy := handoffPolicy(accepted)
	context := controlHistoryTestContext{policies: [][]byte{controlJSON(t, policy)}}
	context.records = [][]byte{controlJSON(t, accepted), controlJSON(t, rejected)}
	i := validation.Invocation{Instance: rejected, Context: context}
	if err := e.controlOccurrence(i); err != nil {
		t.Fatal(err)
	}
	object(at(rejected, "occurrence", "observed"))["state_revision"] = json.Number("0")
	context.records[1] = controlJSON(t, rejected)
	i.Context = context
	if err := e.controlOccurrence(i); err == nil {
		t.Error("accepted incorrect rejected-attempt observed state")
	}
	object(at(rejected, "occurrence", "observed"))["state_revision"] = json.Number("1")
	context.records = [][]byte{controlJSON(t, rejected)}
	i.Context = context
	if err := e.controlOccurrence(i); err == nil {
		t.Error("accepted truncated participant prefix")
	}
	context.records = [][]byte{controlJSON(t, accepted), controlJSON(t, rejected)}
	object(array(policy["states"])[0])["authority_status"] = "revoked"
	context.policies = [][]byte{controlJSON(t, policy)}
	i.Context = context
	if err := e.controlOccurrence(i); err == nil {
		t.Error("accepted revoked source controller")
	}
}

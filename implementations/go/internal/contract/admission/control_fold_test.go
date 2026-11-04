package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func controlProposalAndApproval(t *testing.T) (map[string]any, map[string]any, map[string]any) {
	t.Helper()
	proposal := fixtureObject(t, "fixtures/participant-runtime/participant-control-occurrence-v2/valid/accepted-handoff.json")
	approval := fixtureObject(t, "fixtures/participant-runtime/participant-control-occurrence-v2/valid/accepted-handoff.json")
	policy := handoffPolicy(proposal)
	p, a := object(proposal["occurrence"]), object(approval["occurrence"])
	delete(p, "completion_evidence_ref")
	delete(a, "completion_evidence_ref")
	p["kind"], p["permitted_transition_ref"], p["proposal_id"], p["proposal_revision"], p["admission_status"], p["action_contract_ref"], p["payload_ref"] = "proposal", "transition.propose", "proposal.one", jsonOne, "not-admitted", "actions.scan", "payload.one"
	approval["event_id"], approval["actor_ref"] = "control.approval", "controller.supervised"
	a["kind"], a["permitted_transition_ref"], a["controller_ref"] = "approval", "transition.approve", "controller.supervised"
	a["prior_state_ref"], a["resulting_state_ref"] = p["resulting_state_ref"], p["resulting_state_ref"]
	a["expected_state_revision"], a["resulting_state_revision"], a["expected_history_head"], a["occurrence_revision"], a["effective_order"] = jsonOne, json.Number("2"), jsonOne, json.Number("2"), json.Number("20")
	a["proposal_ref"], a["proposal_revision"], a["decision_ref"], a["decision_revision"] = "proposal.one", jsonOne, "decision.one", jsonOne
	policy["transitions"] = []any{
		map[string]any{"transition_ref": "transition.propose", "kind": "proposal", "from_state_ref": p["prior_state_ref"], "to_state_ref": p["resulting_state_ref"], "valid_from_order": jsonZero, "valid_until_order": json.Number("1000"), "target_kinds": []any{}},
		map[string]any{"transition_ref": "transition.approve", "kind": "approval", "from_state_ref": a["prior_state_ref"], "to_state_ref": a["resulting_state_ref"], "valid_from_order": jsonZero, "valid_until_order": json.Number("1000"), "target_kinds": []any{"proposal"}},
	}
	return proposal, approval, policy
}

func TestControlV2TargetCannotAuthorizeASecondDecision(t *testing.T) {
	e := boundTestOwner(t)
	proposal, approval, policy := controlProposalAndApproval(t)
	context := controlHistoryTestContext{policies: [][]byte{controlJSON(t, policy)}}
	context.records = [][]byte{controlJSON(t, proposal), controlJSON(t, approval)}
	i := validation.Invocation{Instance: approval, Context: context}
	if err := e.controlOccurrence(i); err != nil {
		t.Fatal(err)
	}
	approval["event_id"] = "control.second-decision"
	a := object(approval["occurrence"])
	a["decision_ref"], a["expected_state_revision"], a["resulting_state_revision"], a["expected_history_head"], a["occurrence_revision"], a["effective_order"] = "decision.two", json.Number("2"), json.Number("3"), json.Number("2"), json.Number("3"), json.Number("30")
	context.records = append(context.records, controlJSON(t, approval))
	i.Context = context
	if err := e.controlOccurrence(i); err == nil {
		t.Error("used a decided proposal as fresh decision authority")
	}
}

func TestControlV2FiniteScriptUsesExactCursorAndWindow(t *testing.T) {
	e := boundTestOwner(t)
	proposal, approval, policy := controlProposalAndApproval(t)
	for _, value := range []any{proposal, approval} {
		object(at(value, "policy"))["form"] = "finite-script"
	}
	object(at(policy, "pin"))["form"] = "finite-script"
	object(at(proposal, "occurrence"))["script_step_ref"] = "step.propose"
	object(at(approval, "occurrence"))["script_step_ref"] = "step.approve"
	policy["script_steps"] = []any{map[string]any{"step_ref": "step.propose", "transition_ref": "transition.propose", "expected_state_revision": jsonZero}, map[string]any{"step_ref": "step.approve", "transition_ref": "transition.approve", "expected_state_revision": jsonOne, "target_kind": "proposal", "target_step_ref": "step.propose"}}
	context := controlHistoryTestContext{policies: [][]byte{controlJSON(t, policy)}}
	context.records = [][]byte{controlJSON(t, proposal), controlJSON(t, approval)}
	i := validation.Invocation{Instance: approval, Context: context}
	if err := e.controlOccurrence(i); err != nil {
		t.Fatal(err)
	}
	object(at(approval, "occurrence"))["script_step_ref"] = "step.propose"
	context.records[1] = controlJSON(t, approval)
	i.Context = context
	if err := e.controlOccurrence(i); err == nil {
		t.Error("accepted stale script cursor")
	}
	object(at(approval, "occurrence"))["script_step_ref"] = "step.approve"
	context.records[1] = controlJSON(t, approval)
	step := object(array(policy["script_steps"])[1])
	step["valid_from_order"], step["valid_until_order"] = jsonZero, json.Number("15")
	context.policies = [][]byte{controlJSON(t, policy)}
	i.Context = context
	if err := e.controlOccurrence(i); err == nil {
		t.Error("accepted record outside evaluated script window")
	}
}

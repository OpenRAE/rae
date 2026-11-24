package processor

import (
	"encoding/json"
	"testing"
)

func TestParticipantBudgetKeepsExactLimitsAndOwnerIdentity(t *testing.T) {
	state := compilerState{}
	limit := json.Number("184467440737095516160")
	policy := participantExecutionSource{MaxActionAttempts: limit, MaxInFlight: "2"}
	owners, demands, fairness := state.participantBudget(policy, []string{"participant.behavior.worker"})
	if state.err != nil || len(owners) != 1 || len(demands) != 2 || demands[0].Limit != limit || demands[0].WindowTicks == nil || *demands[0].WindowTicks != limit || demands[1].WindowTicks != nil || fairness.Weight != "1" {
		t.Fatalf("legacy budget lost its exact limits or defaults: %#v %#v %#v %v", owners, demands, fairness, state.err)
	}
	policy.ResourceBudget = &participantBudget{Owners: map[string]participantBudgetOwner{"owner": {Kind: "participant", Ref: "worker"}}, Dimensions: map[string]participantBudgetDimension{"capacity": {OwnerRef: "owner", Limit: limit, Reservation: "1", EvidenceRefs: []string{"evidence.capacity"}}}}
	owners, demands, _ = state.participantBudget(policy, []string{"participant.behavior.worker"})
	if state.err != nil || owners[0].Address != "participant.behavior.worker" || demands[0].Provenance != "authored" || demands[0].Limit != limit || demands[0].OwnerAddress != owners[0].Address {
		t.Fatalf("authored budget lost owner or provenance: %#v %#v %v", owners, demands, state.err)
	}
	state.participantBudget(policy, []string{"participant.behavior.other"})
	if state.err == nil {
		t.Fatal("unresolved participant owner was accepted")
	}
}

func TestMixedPolicyAddressHasNoEmptySegment(t *testing.T) {
	state := compilerState{}
	policy := state.compileMixed("policy", json.RawMessage(`{"semantics":"rev1","participant_ref":"worker","policy_revision":"1","initial_state_ref":"self","controller_states":{},"permitted_transitions":{},"script_steps":[]}`))
	if state.err != nil || policy.policy == nil || policy.policy.Address != "participant.behavior-specification.policy.mixed-control-policy" {
		t.Fatalf("invalid policy address: %#v %v", policy.policy, state.err)
	}
}

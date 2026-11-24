package processor

import (
	"encoding/json"
	"testing"
)

func TestParticipantContextCollectsDirectAndReusableSelections(t *testing.T) {
	state := compilerState{input: compilerInput{order: map[string][]string{"/agents": {"worker"}, "/behavior_specifications": {"shared"}}, aliases: map[string][]string{"asset": {"control_context_assets.asset"}}}, participantRoles: map[string]string{"worker": "green"}}
	err := json.Unmarshal([]byte(`{"agents":{"worker":{"control_context":{"direct":{"declaration_ref":"asset","asset_ref":{"asset_id":"a"},"disposition":"withheld"}}}},"behavior_specifications":{"shared":{"participant_role_refs":["green"],"control_context":{"reusable":{"declaration_ref":"asset","asset_ref":{"asset_id":"a"},"disposition":"selected"}}}}}`), &state.input.model)
	if err != nil {
		t.Fatal(err)
	}
	state.compileControlContexts()
	selections := state.contextByParticipant["agents.worker"]
	if state.err != nil || len(selections) != 2 || selections[0].SlotID != "direct" || selections[1].SlotID != "reusable" || selections[1].OwnerAddress != "behavior_specifications.shared" || len(state.contextByOwner["behavior_specifications.shared"]) != 1 {
		t.Fatalf("lost selection ownership or order: %#v %v", selections, state.err)
	}
}

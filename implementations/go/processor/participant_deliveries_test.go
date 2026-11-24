package processor

import (
	"encoding/json"
	"slices"
	"testing"
)

func TestParticipantDeliveryKeepsOccurrenceAndControlRelations(t *testing.T) {
	state := compilerState{input: compilerInput{references: map[string]map[string][]string{"targetable": {"source": {"content.source"}, "result": {"content.result"}, "evidence": {"content.evidence"}}, "authority-scope": {"scope": {"nodes.target"}}}}, runtimeReferences: map[string]string{"content.source": "provision.content.source", "content.result": "provision.content.result", "content.evidence": "provision.content.evidence", "nodes.target": "provision.node.target"}}
	raw := json.RawMessage(`{"participant_ref":"worker","inject_ref":"message","occurrence":{"event_ref":"send","script_ref":"sequence","story_ref":"story"},"source_item_ref":"source","result_item_ref":"result","observation_boundary_ref":"view","temporal_constraint_refs":["window"],"evidence_requirement_refs":["receipt"],"control":{"semantics":"mixed-control-policy-occurrence/rev1","permitted_transition_ref":"allow","controller_ref":"self","authority_scope_refs":["scope"],"evidence_refs":["evidence"]}}`)
	var source participantDeliverySource
	if err := json.Unmarshal(raw, &source); err != nil {
		t.Fatal(err)
	}
	state.compileParticipantDelivery("policy", "message", raw, source)
	if state.err != nil || len(state.model.ParticipantResources) != 1 {
		t.Fatalf("delivery = %#v %v", state.model, state.err)
	}
	resource := state.model.ParticipantResources[0]
	if !slices.Equal(resource.OrderingDependencies, []string{"orchestration.inject.message", "orchestration.event.send", "orchestration.script.sequence", "orchestration.story.story"}) || !slices.Contains(resource.RefreshDependencies, "provision.node.target") || !slices.Contains(resource.RefreshDependencies, "participant.behavior-specification.policy.permitted-transition.allow") {
		t.Fatalf("lost occurrence or authority relation: %#v", resource)
	}
	var delivery participantDelivery
	if err := json.Unmarshal(resource.Payload.JSON(), &delivery); err != nil {
		t.Fatal(err)
	}
	if delivery.Control == nil || delivery.Control.ControllerAddress != "participant.behavior.worker" || delivery.ControlTransitionAddress != "" || delivery.SourceItemAddress != "provision.content.source" {
		t.Fatalf("changed permission into occurrence: %#v", delivery)
	}
	state.model.ParticipantResources = nil
	source.SourceItemRef = "missing"
	state.compileParticipantDelivery("policy", "message", raw, source)
	if len(state.model.ParticipantResources) != 0 || len(state.model.Diagnostics) != 1 || state.model.Diagnostics[0].Code != "participant.inject-delivery-item-unaddressable" {
		t.Fatalf("compiled unaddressable delivery: %#v", state.model)
	}
}

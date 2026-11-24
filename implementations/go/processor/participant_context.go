package processor

import (
	"encoding/json"
	"strings"
)

// SDL owns pin, scope and slot-conflict checks. These indexes retain the
// admitted selections in both participant and declaration-owner order.
func (state *compilerState) compileControlContexts() {
	state.contextByParticipant = map[string][]controlContextSelection{}
	state.contextByOwner = map[string][]controlContextSelection{}
	add := func(owner, participant, pointer string, bindings map[string]json.RawMessage) {
		selections := state.controlContext(owner, participant, bindings, pointer)
		key := "agents." + participant
		state.contextByParticipant[key] = append(state.contextByParticipant[key], selections...)
		state.contextByOwner[owner] = append(state.contextByOwner[owner], selections...)
	}
	agents := fieldValue(state.input.model.Agents)
	for _, name := range orderedNames(agents, state.names("agents")) {
		add("agents."+name, name, "/agents/"+escapePointer(name)+"/control_context", fieldValue(agents[name].ControlContext))
	}
	specifications := fieldValue(state.input.model.BehaviorSpecifications)
	for _, name := range orderedNames(specifications, state.names(termBehaviorSpecifications)) {
		specification := specifications[name]
		owner := "behavior_specifications." + name
		participants, _ := state.selectParticipants(participantSelector{fieldValue(specification.ParticipantRefs), fieldValue(specification.ParticipantRoleRefs)}, owner, false)
		for _, participant := range participants {
			add(owner, strings.TrimPrefix(participant, "participant.behavior."), "/behavior_specifications/"+escapePointer(name)+"/control_context", fieldValue(specification.ControlContext))
		}
	}
}

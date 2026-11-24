package processor

import "encoding/json"

type entityMetadata struct {
	Role     json.RawMessage            `json:"role"`
	Entities map[string]json.RawMessage `json:"entities"`
}

func (state *compilerState) compileMetadata() {
	state.entities = map[string]entityMetadata{}
	var entities func(map[string]json.RawMessage, string, string)
	entities = func(entries map[string]json.RawMessage, prefix, pointer string) {
		for _, name := range orderedNames(entries, state.input.order[pointer]) {
			qualified := prefix + name
			raw := entries[name]
			var entity entityMetadata
			if err := json.Unmarshal(raw, &entity); err != nil {
				state.err = invalidCompiled()
				return
			}
			state.entities[qualified] = entity
			state.model.Definitions = append(state.model.Definitions, Definition{Address: "entities." + qualified, Name: qualified, Kind: "entity", Payload: ResourcePayload{data: raw}})
			entities(entity.Entities, qualified+".", pointer+"/"+escapePointer(name)+"/entities")
		}
	}
	roots := map[string]json.RawMessage{}
	for name, entity := range fieldValue(state.input.model.Entities) {
		roots[name] = rawJSON(entity)
	}
	entities(roots, "", "/entities")
	agents := fieldValue(state.input.model.Agents)
	state.participantRoles = map[string]string{}
	for _, name := range orderedNames(agents, state.names("agents")) {
		agent := agents[name]
		role := rawString(fieldValue(agent.Role))
		affiliations := fieldValue(agent.Affiliations)
		if role == "" && len(affiliations) == 1 {
			role = rawString(state.entities[affiliations[0]].Role)
		}
		state.participantRoles[name] = role
		state.model.Definitions = append(state.model.Definitions, Definition{Address: "agents." + name, Name: name, Kind: "agent", Payload: ResourcePayload{data: state.participantAgentSource(name)}})
	}
	relationships := fieldValue(state.input.model.Relationships)
	for _, name := range orderedNames(relationships, state.names("relationships")) {
		state.model.Definitions = append(state.model.Definitions, Definition{Address: "relationships." + name, Name: name, Kind: "relationship", Payload: ResourcePayload{data: rawJSON(relationships[name])}})
	}
}

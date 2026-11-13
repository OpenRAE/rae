package processor

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

// These source projections preserve the admitted constructor's empty-context
// omission rule. The retained typed input still includes its default map.
func (state *compilerState) participantAgentSource(name string) json.RawMessage {
	source := fieldValue(state.input.model.Agents)[name]
	if len(fieldValue(source.ControlContext)) == 0 {
		source.ControlContext = binding.Field[map[string]json.RawMessage]{}
	}
	return rawJSON(source)
}
func (state *compilerState) participantSpecificationSource(name string) json.RawMessage {
	source := fieldValue(state.input.model.BehaviorSpecifications)[name]
	if len(fieldValue(source.ControlContext)) == 0 {
		source.ControlContext = binding.Field[map[string]json.RawMessage]{}
	}
	return rawJSON(source)
}

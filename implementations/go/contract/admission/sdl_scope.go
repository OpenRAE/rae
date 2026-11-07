package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"

// ResolveSDLObservationScope projects an SDL pointer to its semantic address.
// Forwarding agents use their declared identity; other lists retain positions.
// The recursive-structure default ceilings apply. No admission is granted.
func ResolveSDLObservationScope(value any, pointer string) (string, string, error) {
	tokens := jsonpointer.Tokens(pointer)
	if len(pointer) > 4096 || len(tokens) > 32 || jsonpointer.FromTokens(tokens) != pointer {
		return "", "", invalid()
	}
	source, semantic := []string{}, []string{}
	current := value
	remaining := 4096
	for _, token := range tokens {
		var fields []string
		if len(source) == 1 && source[0] == termForwardingAgents {
			fields = []string{"forwarding_agent_id"}
		}
		next, sourceToken, semanticToken, err := materializationAddressStep(current, token, fields, &remaining)
		if err != nil {
			return "", "", err
		}
		source = append(source, sourceToken)
		semantic = append(semantic, semanticToken)
		current = next
	}
	return jsonpointer.FromTokens(source), jsonpointer.FromTokens(semantic), nil
}

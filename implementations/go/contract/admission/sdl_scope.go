package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"

// ResolveSDLObservationScope projects an SDL pointer to its semantic address.
// Forwarding agents use their declared identity; other lists retain positions.
// The recursive-structure default ceilings apply. No admission is granted.
func ResolveSDLObservationScope(value any, pointer string) (string, string, error) {
	return resolveSDLObservationScope(value, pointer, nil)
}

// ResolveSDLObservationScopeWithProfiles uses registered collection identities
// through the same address-step owner as ordinary SDL observation scopes.
func ResolveSDLObservationScopeWithProfiles(value any, pointer string, profiles []RealizationCollectionProfile) (string, string, error) {
	if len(profiles) == 0 {
		return resolveSDLObservationScope(value, pointer, nil)
	}
	limits := DefaultConstraintLimits()
	if len(profiles) > limits.MaxMembers {
		return "", "", invalid()
	}
	normalizer := literalNormalizer{limits: limits, metadata: RealizationNormalizationMetadata{CollectionProfiles: profiles}, profiles: map[string]RealizationCollectionProfile{}, optional: map[string]bool{}, visited: map[string]bool{}}
	closure := RealizationClosure{Posture: termClosed, Universe: "sdl-collection-members/v1", Profile: "recursive-realization-constraint/v1"}
	if failure, err := normalizer.admitMetadata("recursive-realization-constraint/v1", closure); err != nil || failure != nil {
		return "", "", invalid()
	}
	return resolveSDLObservationScope(value, pointer, normalizer.profiles)
}
func resolveSDLObservationScope(value any, pointer string, profiles map[string]RealizationCollectionProfile) (string, string, error) {
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
		if profile, present := profiles[jsonpointer.FromTokens(source)]; present {
			fields = profile.IdentityFields
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

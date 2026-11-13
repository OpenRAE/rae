package realization

import "github.com/OpenRAE/rae/implementations/go/contract/admission"

// HasRequiredObservationSupport checks scope and source independently. A
// stronger scope cannot substitute for a specifically required evidence source.
func HasRequiredObservationSupport(requirement admission.Fragment, declarations []admission.Fragment, observationKind string) (bool, error) {
	if admission.CheckFragment(requirement, admission.CompiledRealizationRequirement) != nil || len(declarations) > 16384 || len(observationKind) > 256 {
		return false, invalidRealization()
	}
	for _, declaration := range declarations {
		if admission.CheckFragment(declaration, admission.RealizationSupport) != nil {
			return false, invalidRealization()
		}
	}
	demand := ownedProjection[map[string]any](requirement.Document())
	for _, declaration := range declarations {
		capabilities, _ := ownedProjection[map[string]any](declaration.Document())["observation_capabilities"].(map[string]any)
		capability, present := capabilities[observationKind].(map[string]any)
		if !present {
			continue
		}
		if observationSatisfied(capability["verification_scope"], capability["observation_strength"], demand["verification_scope"], demand["required_observation_strength"]) {
			return true, nil
		}
	}
	return false, nil
}

func observationSatisfied(actualScope, actualSource, requiredScope, requiredSource any) bool {
	scopeSatisfied := requiredScope == nil || requiredScope == "" || actualScope == requiredScope || actualScope == termConfiguration && requiredScope == termPresence
	sourceSatisfied := actualSource == requiredSource
	if requiredSource == nil || requiredSource == "" {
		sourceSatisfied = actualSource == "daemon-observed" || actualSource == "guest-observed"
	}
	return scopeSatisfied && sourceSatisfied
}

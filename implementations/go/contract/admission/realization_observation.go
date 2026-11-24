package admission

const (
	termObservedOperatingSystem = "operating-system"
	termObservedGuest           = "guest-observed"
)

// realizationObservation checks the existing published model's value-bearing
// evidence rules. Schema admission already checks the field grammar and bounds.
func (e *Validator) realizationObservation(v any) error {
	if stringAt(v, "observation_strength") == postureNone {
		return invalid()
	}
	switch stringAt(v, "requirement_kind") {
	case termCompute:
		return require(at(v, "observed_value") != nil && at(v, "operating_system") == nil && boundRealizationObservation(v) && e.vocabularyTerm("compute-substrates", stringAt(v, "observed_value")))
	case termObservedOperatingSystem:
		return require(at(v, "observed_value") == nil && at(v, "operating_system") != nil && boundRealizationObservation(v) && stringAt(v, "observation_strength") == termObservedGuest)
	default:
		return require(!valueBearingRealizationObservation(v))
	}
}
func boundRealizationObservation(v any) bool {
	if at(v, "binding_verified") != true {
		return false
	}
	for _, field := range []string{"operation_id", "envelope_digest", "configuration_digest", "observer_version", termSequence} {
		if at(v, field) == nil {
			return false
		}
	}
	return true
}
func valueBearingRealizationObservation(v any) bool {
	if at(v, "binding_verified") == true {
		return true
	}
	for _, field := range []string{"observed_value", "operating_system", "operation_id", "envelope_digest", "configuration_digest", "observer_version", termSequence} {
		if at(v, field) != nil {
			return true
		}
	}
	return false
}
func (e *Validator) observedOperatingSystemIdentity(v any) error {
	// The same vocabulary and core family/distribution join governs both
	// capability rows and observations; the observation schema owns its release.
	return e.operatingSystemCapability(v)
}

package realization

// The published observation owner checks the disclosure shape. These private
// predicates additionally bind its claims to this independently admitted plan
// and apparatus, as the source operating-system binding owner requires.
func (s *evaluationState) observationApparatusBound(observation evaluatedObservation) bool {
	if s.options.Envelope == nil {
		return false
	}
	configuration := sourceValue(s.options.Envelope.Configuration)
	return observation.BindingVerified && observation.EnvelopeDigest == sourceValue(s.options.Envelope.Digest) && observation.ConfigurationDigest == sourceValue(configuration.ConfigurationDigest)
}

func (s *evaluationState) operatingSystemObservationBound(observation evaluatedObservation) bool {
	if s.options.Manifest == nil || s.options.Envelope == nil || s.plan.OperationID == "" || observation.OperationID != s.plan.OperationID {
		return false
	}
	// Unlike substrate selection on an unchanged operation, guest OS evidence
	// must identify the exact current operation; it has no no-op exception.
	return checkResolutionEnvelopeIdentity(s.plan.Envelope, *s.options.Envelope) == nil && s.observationApparatusBound(observation)
}

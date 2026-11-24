package realization

import (
	"bytes"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type evaluatedObservationDemand = admission.ObservationDemandSelection

func (s *evaluationState) substrateObservationDemand(requirement Requirement) (bool, error) {
	return admission.SelectObservationDemand(s.plan.Demands, requirement.GoverningScope, requirement.Address, requirement.Kind, "collection")
}
func (s *evaluationState) evaluateSubstrate(requirement Requirement, operation evaluatedOperation) (*diagnostic.Diagnostic, *Provenance, error) {
	if s.options.Manifest == nil || s.options.Envelope == nil {
		return substrateEvidenceFailure(requirement), nil, nil
	}
	mechanism := s.substrateMechanism()
	selected, err := s.substrateObservationDemand(requirement)
	if err != nil {
		return nil, nil, err
	}
	if selected {
		return s.evaluateSubstrateObservation(requirement, operation, mechanism)
	}
	if mechanism == "" || !s.substrateEnvelopeMatches() {
		return supportFinding(requirement, "runtime.backend-contract-invalid", "Backend returned no bound substrate selection for '"+requirement.FieldPath+"'."), nil, nil
	}
	return substrateSelectionResult(requirement, mechanism)
}
func (s *evaluationState) substrateMechanism() string {
	for _, concern := range sourceValue(s.options.Envelope.Concerns) {
		if string(sourceValue(concern.Concern)) == termComputeSubstrate {
			var mechanism string
			if json.Unmarshal(sourceValue(concern.Mechanism), &mechanism) != nil {
				return ""
			}
			return mechanism
		}
	}
	return ""
}
func (s *evaluationState) substrateEnvelopeMatches() bool {
	if s.options.Manifest == nil || s.options.Envelope == nil || len(s.plan.Envelope) == 0 || bytes.Equal(s.plan.Envelope, []byte("null")) {
		return false
	}
	var planned, returned, declared any
	if json.Unmarshal(s.plan.Envelope, &planned) != nil || json.Unmarshal(s.snapshot.Envelope, &returned) != nil || json.Unmarshal(sourceValue(s.options.Manifest.RealizationEnvelope), &declared) != nil {
		return false
	}
	return payloadEqual(planned, returned) && payloadEqual(planned, declared)
}
func (s *evaluationState) evaluateSubstrateObservation(requirement Requirement, operation evaluatedOperation, mechanism string) (*diagnostic.Diagnostic, *Provenance, error) {
	observation, present := s.observation(requirement)
	if !present || !observationSatisfied(observation.Scope, observation.Strength, requirement.ObservationScope, requirement.ObservationStrength) || !s.manifestCorroborates(requirement, observation) {
		return substrateEvidenceFailure(requirement), nil, nil
	}
	bound := s.substrateEnvelopeMatches() && mechanism != "" && payloadEqual(mechanism, observation.Value) && s.observationApparatusBound(observation)
	operationBound := operation.Action == "unchanged" || s.plan.OperationID != "" && observation.OperationID == s.plan.OperationID
	if !bound || !operationBound {
		return substrateEvidenceFailure(requirement), nil, nil
	}
	return substrateSelectionResult(requirement, observation.Value)
}
func substrateSelectionResult(requirement Requirement, mechanism any) (*diagnostic.Diagnostic, *Provenance, error) {
	if requirement.ValueDomain != nil {
		admitted, err := domainAdmitsValue(requirement.ValueDomain, mechanism)
		if err != nil {
			return nil, nil, err
		}
		if !admitted {
			return silentApproximation(requirement), nil, nil
		}
	}
	if requirement.Posture == nil {
		return nil, nil, invalidRealization()
	}
	return nil, realizationProvenance(requirement, *requirement.Posture == termExact), nil
}
func substrateEvidenceFailure(requirement Requirement) *diagnostic.Diagnostic {
	return supportFinding(requirement, "runtime.backend-contract-invalid", "Backend returned no independently observed, operation- and apparatus-bound compute substrate for '"+requirement.FieldPath+"'; plan values, handles, and configuration claims are not realization evidence.")
}

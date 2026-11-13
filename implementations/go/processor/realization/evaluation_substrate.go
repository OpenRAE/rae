package realization

import (
	"bytes"
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type evaluatedObservationDemand struct {
	Scope      string                   `json:"scope"`
	Purpose    string                   `json:"purpose"`
	Mode       string                   `json:"mode"`
	Collection string                   `json:"collection"`
	Selectors  []evaluatedFieldSelector `json:"selectors"`
}
type evaluatedFieldSelector struct {
	Scope      string   `json:"semantic_scope"`
	Excluded   []string `json:"excluded_scopes"`
	Components []string `json:"component_refs"`
	Kind       string   `json:"data_kind"`
	Names      []string `json:"names"`
}

func scopeContains(parent, child string) bool {
	return parent == child || parent == "" || strings.HasPrefix(child, parent+"/")
}
func (s *evaluationState) substrateObservationDemand(requirement Requirement) bool {
	scope := strings.TrimPrefix(requirement.GoverningScope, "#")
	for _, demand := range s.plan.Demands {
		if !scopeContains(demand.Scope, scope) || demand.Purpose == "realization-description" || demand.Collection != "require" {
			continue
		}
		if !slices.Contains([]string{"selected", "exhaustive", "operational-only"}, demand.Mode) || s.narrowerDemandExists(demand, scope) {
			continue
		}
		for _, selector := range demand.Selectors {
			if selector.selects(scope, requirement.Address, requirement.Kind) {
				return true
			}
		}
	}
	return false
}
func (s *evaluationState) narrowerDemandExists(demand evaluatedObservationDemand, scope string) bool {
	for _, candidate := range s.plan.Demands {
		if candidate.Purpose == demand.Purpose && scopeContains(candidate.Scope, scope) && strings.Count(candidate.Scope, "/") > strings.Count(demand.Scope, "/") {
			return true
		}
	}
	return false
}
func (selector evaluatedFieldSelector) selects(scope, address, kind string) bool {
	if !scopeContains(selector.Scope, scope) || selector.Kind != "field" || !slices.Contains(selector.Names, kind) {
		return false
	}
	if len(selector.Components) > 0 && !slices.Contains(selector.Components, address) {
		return false
	}
	for _, excluded := range selector.Excluded {
		if scopeContains(excluded, scope) {
			return false
		}
	}
	return true
}
func (s *evaluationState) evaluateSubstrate(requirement Requirement, operation evaluatedOperation) (*diagnostic.Diagnostic, *Provenance, error) {
	if s.options.Manifest == nil || s.options.Envelope == nil {
		return substrateEvidenceFailure(requirement), nil, nil
	}
	mechanism := s.substrateMechanism()
	if s.substrateObservationDemand(requirement) {
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

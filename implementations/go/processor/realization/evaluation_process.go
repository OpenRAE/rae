package realization

import (
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
)

func (s *evaluationState) processProjectionAdmitted(requirement Requirement, input any) (bool, error) {
	if requirement.Kind != termProcessResourceLimits || missingValue(input) {
		return true, nil
	}
	rows, ok := input.([]any)
	if !ok || s.options.Manifest == nil {
		return false, nil
	}
	capabilities, err := s.observedProcessCapabilities(requirement)
	if err != nil {
		return false, err
	}
	actual := requirement
	actual.ValueConstraints = nil
	actual.ProcessResourceLimits = []ProcessResourceLimit{}
	owner, err := realizationOwner()
	if err != nil {
		return false, err
	}
	for _, item := range rows {
		row, err := evaluationProcessRow(item)
		if err != nil {
			return false, nil //nolint:nilerr // Malformed readback is a non-admitted relation result.
		}
		soft, err := admission.AdmitFragment(owner, admission.RealizationValue, row[termSoft], ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
		if err != nil {
			return false, err
		}
		hard, err := admission.AdmitFragment(owner, admission.RealizationValue, row[termHard], ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
		if err != nil {
			return false, err
		}
		actual.ProcessResourceLimits = append(actual.ProcessResourceLimits, ProcessResourceLimit{Resource: ownedProjection[string](row[termResource]), Scope: ownedProjection[string](row[termScope]), Soft: soft, Hard: hard})
	}
	return processDemandsAdmitted(actual, capabilities)
}
func evaluationProcessRow(input any) (map[string]any, error) {
	row, ok := input.(map[string]any)
	if !ok {
		return nil, invalidRealization()
	}
	row = maps.Clone(row)
	delete(row, termIdentityMarker)
	return sharedProcessProjection(row, true)
}
func (s *evaluationState) observedProcessCapabilities(requirement Requirement) ([]processCapability, error) {
	configured := []processCapability{}
	if s.options.Envelope != nil {
		for _, capability := range sourceValue(sourceValue(s.options.Envelope.Configuration).ProcessResourceLimits) {
			decoded, err := decodeProcessCapability(capability)
			if err != nil {
				return nil, err
			}
			configured = append(configured, decoded)
		}
	}
	result := []processCapability{}
	for _, declaration := range s.supportDeclarations(requirement) {
		if !observationPostureSupported(requirement, declaration) || !sufficientlyObserved(requirement, []supportDeclaration{declaration}) {
			continue
		}
		for _, capability := range declaration.processLimits {
			if slices.ContainsFunc(configured, capability.equal) {
				result = append(result, capability)
			}
		}
	}
	return result, nil
}
func (s *evaluationState) processRealization(requirement Requirement, expected, observed any) (bool, bool, error) {
	if requirement.Kind != termProcessResourceLimits {
		return true, false, nil
	}
	admitted, err := s.processProjectionAdmitted(requirement, observed)
	if err != nil || !admitted {
		return admitted, false, err
	}
	if *requirement.Posture != termConstrained {
		return true, payloadEqual(expected, observed), nil
	}
	first, firstOK := evaluationProcessIndex(expected)
	second, secondOK := evaluationProcessIndex(observed)
	if !firstOK || !secondOK || len(first) != len(second) {
		return false, false, nil
	}
	exact := true
	for identity, before := range first {
		after, present := second[identity]
		if !present {
			return false, false, nil
		}
		for _, leaf := range []string{termSoft, termHard} {
			if !processLeafAdmitted(requirement, identity, leaf, before[leaf], after[leaf]) {
				return false, false, nil
			}
			exact = exact && payloadEqual(before[leaf], after[leaf])
		}
	}
	return true, exact, nil
}
func evaluationProcessIndex(input any) (map[string]map[string]any, bool) {
	items, ok := input.([]any)
	if !ok {
		return nil, false
	}
	result := map[string]map[string]any{}
	for _, item := range items {
		row, err := evaluationProcessRow(item)
		if err != nil {
			return nil, false
		}
		identity, err := projectionDigest(map[string]any{termResource: row[termResource], termScope: row[termScope], termSubject: row[termSubject]})
		if err != nil {
			return nil, false
		}
		result[identity] = row
	}
	return result, true
}
func processLeafAdmitted(requirement Requirement, identity, leaf string, before, after any) bool {
	for _, constraint := range requirement.ValueConstraints {
		if constraint.IdentityDigest != identity || constraint.Leaf != leaf {
			continue
		}
		for _, candidate := range ownedProjection[[]any](constraint.AllowedValues.Document()) {
			if domain.Equal(candidate, after) {
				return true
			}
		}
		return false
	}
	return payloadEqual(before, after)
}

package realization

import (
	"maps"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func (s *evaluationState) evaluatePlannedValues(cleanup bool) (Evaluation, error) {
	result := Evaluation{Diagnostics: []diagnostic.Diagnostic{}, Provenance: []Provenance{}}
	requirements, err := s.plannedRequirements()
	if err != nil {
		return plannedEvaluationFailure(err, s.plan)
	}
	views := map[plannedConcernKey]Requirement{}
	for _, requirement := range requirements {
		views[plannedConcernKey{requirement.Address, requirement.Kind}] = requirement
	}
	defaults := map[string]any{}
	for _, authority := range s.plan.Authority {
		finding, provenance, evaluateErr := s.evaluatePlannedAuthority(authority, views, defaults, cleanup)
		if evaluateErr != nil {
			return Evaluation{}, evaluateErr
		}
		if finding != nil {
			result.Diagnostics = append(result.Diagnostics, *finding)
		}
		if provenance != nil && !cleanup {
			result.Provenance = append(result.Provenance, *provenance)
		}
	}
	if err := s.evaluatePlannedConstraints(&result, cleanup); err != nil {
		return Evaluation{}, err
	}
	return result, nil
}
func (s *evaluationState) evaluatePlannedConstraints(result *Evaluation, cleanup bool) error {
	constraints, err := s.plannedConstraintRequirements()
	if err != nil {
		return err
	}
	for _, requirement := range constraints {
		finding, provenance, evaluateErr := s.evaluate(requirement)
		if evaluateErr != nil {
			return evaluateErr
		}
		if finding != nil {
			result.Diagnostics = append(result.Diagnostics, *finding)
		}
		if provenance != nil && !cleanup {
			result.Provenance = append(result.Provenance, *provenance)
		}
	}
	return nil
}

func (s *evaluationState) evaluatePlannedAuthority(authority plannedAuthority, views map[plannedConcernKey]Requirement, defaults map[string]any, cleanup bool) (*diagnostic.Diagnostic, *Provenance, error) {
	if authority.Mode == termClosed {
		finding, err := s.plannedClosedFinding(authority, defaults)
		return finding, nil, err
	}
	requirement := views[plannedConcernKey{authority.Address, authority.Kind}]
	if cleanup {
		requirement = s.cleanupRequirement(requirement)
	}
	finding, provenance, err := s.evaluate(requirement)
	if err != nil || finding != nil {
		return finding, provenance, err
	}
	if authority.Mode == termConstrained {
		finding, err = s.plannedRuntimeBoundsFinding(authority)
		if err != nil || finding != nil {
			return finding, nil, err
		}
	}
	return nil, provenance, nil
}

func (s *evaluationState) plannedRuntimeBoundsFinding(authority plannedAuthority) (*diagnostic.Diagnostic, error) {
	definition, known := concernDefinitionFor(authority.Kind)
	if !known {
		return nil, invalidRealization()
	}
	// Bounds and the registered evaluator must consume the same realized
	// concern. OS identity comes exclusively from its dedicated disclosure.
	realized := s.concernValue(Requirement{Address: authority.Address, FieldPath: authority.FieldPath, Domain: authority.Domain, Kind: authority.Kind}, definition.payload)
	if missingValue(realized) {
		return plannedMissingBoundFinding(authority), nil
	}
	// Portable scalar bounds use the legacy canonical projection even when
	// recursive authority separately retains source collection order.
	projected, err := projectEvaluationConcern(Requirement{Kind: authority.Kind}, realized, true)
	if unexpected := plannedUnexpected(err); unexpected != nil {
		return nil, unexpected
	}
	valid := err == nil
	if valid {
		lookup := plannedBoundLookup{input: projected}
		for _, bound := range authority.Bounds {
			admitted, boundErr := lookup.admits(bound)
			if boundErr != nil {
				return nil, boundErr
			}
			if !admitted {
				valid = false
				break
			}
		}
	}
	if !valid {
		return plannedRuntimeBoundFailure(authority), nil
	}
	return nil, nil //nolint:nilnil // No bound finding is a valid optional result.
}

func plannedMissingBoundFinding(authority plannedAuthority) *diagnostic.Diagnostic {
	if observationKind(authority.Kind) == termOperatingSystem && len(authority.Bounds) > 0 {
		return plannedRuntimeBoundFailure(authority)
	}
	return nil
}
func plannedRuntimeBoundFailure(authority plannedAuthority) *diagnostic.Diagnostic {
	return plannedFailure(authority, "runtime.backend-contract-invalid", "Backend cannot satisfy resolved realization authority for '"+authority.Kind+"'.")
}

func (s *evaluationState) plannedClosedFinding(authority plannedAuthority, defaults map[string]any) (*diagnostic.Diagnostic, error) {
	operation, declaredPresent := s.operations[authority.Address]
	entry, realizedPresent := s.snapshot.Entries[authority.Address]
	if !declaredPresent || !realizedPresent {
		return nil, nil //nolint:nilnil // No matching resource makes this authority inapplicable.
	}
	declared := plannedPointerValue(operation.Payload, authority.Pointer)
	realized := plannedPointerValue(entry.Payload, authority.Pointer)
	if missingValue(declared) && !missingValue(realized) {
		cached, err := cachedPlannedPayload(operation, defaults)
		if err != nil {
			return nil, err
		}
		declared = plannedPointerValue(cached, authority.Pointer)
	}
	if missingValue(realized) || !missingValue(declared) && payloadEqual(declared, realized) {
		return nil, nil //nolint:nilnil // Equal complete closed values require no finding.
	}
	return plannedFailure(authority, "runtime.backend-contract-invalid", "Backend materialized closed realization concern '"+authority.Kind+"'."), nil
}
func cachedPlannedPayload(operation evaluatedOperation, defaults map[string]any) (any, error) {
	if cached, present := defaults[operation.Address]; present {
		return cached, nil
	}
	payload, err := plannedDefaultedPayload(operation.Payload)
	var result any = payload
	if err != nil {
		if category, _ := fault.CategoryOf(err); category != fault.InvalidInput {
			return nil, err
		}
		result = missingConcern{}
	}
	defaults[operation.Address] = result
	return result, nil
}

func plannedDefaultedPayload(payload map[string]any) (map[string]any, error) {
	spec, ok := payload[termSpec].(map[string]any)
	if !ok {
		return nil, invalidRealization()
	}
	node, ok := spec[termNode].(map[string]any)
	if !ok {
		return nil, invalidRealization()
	}
	restored, err := restoreRuntimeMarkers(node)
	if err != nil {
		return nil, err
	}
	input, err := nativeValueFragment(restored)
	if err != nil {
		return nil, err
	}
	normalized, _, err := sdl.NormalizeNodeValue(input)
	if err != nil {
		return nil, err
	}
	result := ownedProjection[map[string]any](normalized.Document())
	for _, definition := range concernDefinitions {
		if definition.section == termNodes {
			restorePlannedConcern(result, node, definition.authored)
		}
	}
	output := maps.Clone(payload)
	nodeSpec := maps.Clone(spec)
	nodeSpec[termNode] = result
	output[termSpec] = nodeSpec
	return output, nil
}

func restorePlannedConcern(normalized, original map[string]any, path []string) {
	for _, token := range path[:len(path)-1] {
		next, ok := original[token].(map[string]any)
		if !ok {
			return
		}
		target, ok := normalized[token].(map[string]any)
		if !ok {
			return
		}
		original, normalized = next, target
	}
	if value, present := original[path[len(path)-1]]; present {
		normalized[path[len(path)-1]] = value
	}
}

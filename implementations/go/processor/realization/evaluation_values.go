package realization

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func (s *evaluationState) evaluateOpen(requirement Requirement, realized any) (*diagnostic.Diagnostic, *Provenance, error) {
	if missingValue(realized) {
		if requirement.ObservationScope != "" || requirement.ObservationStrength != "" {
			return invalidObservation(requirement), nil, nil
		}
		return nil, nil, nil
	}
	projected, err := projectEvaluationConcern(requirement, realized, true)
	if err != nil {
		return projectionFailure(requirement, err)
	}
	if finding := s.corroborationDiagnostic(requirement); finding != nil {
		return finding, nil, nil
	}
	admitted, err := s.processProjectionAdmitted(requirement, projected)
	if err != nil {
		return nil, nil, err
	}
	if !admitted {
		return silentApproximation(requirement), nil, nil
	}
	return nil, realizationProvenance(requirement, false), nil
}
func (s *evaluationState) evaluateDeclared(requirement Requirement, declared, realized any) (*diagnostic.Diagnostic, *Provenance, error) {
	if finding := s.corroborationDiagnostic(requirement); finding != nil {
		return finding, nil, nil
	}
	expected, err := projectEvaluationConcern(requirement, declared, false)
	if err != nil {
		if category, _ := fault.CategoryOf(err); category != fault.InvalidInput {
			return nil, nil, err
		}
		expected = missingConcern{}
	}
	observed, err := projectEvaluationConcern(requirement, realized, true)
	if err != nil {
		return projectionFailure(requirement, err)
	}
	admitted, honoured, err := s.processRealization(requirement, expected, observed)
	if err != nil {
		return nil, nil, err
	}
	if !admitted {
		return silentApproximation(requirement), nil, nil
	}
	if requirement.Kind != termProcessResourceLimits || requirement.Structure != nil {
		honoured = payloadEqual(expected, observed)
	}
	rejected, err := projectedConstraintsRejected(requirement, expected, observed, honoured)
	if err != nil {
		return nil, nil, err
	}
	if rejected {
		return silentApproximation(requirement), nil, nil
	}
	if missingValue(realized) {
		return nil, nil, nil
	}
	return nil, realizationProvenance(requirement, honoured), nil
}
func projectionFailure(requirement Requirement, err error) (*diagnostic.Diagnostic, *Provenance, error) {
	if category, _ := fault.CategoryOf(err); category == fault.InvalidInput {
		return invalidObservation(requirement), nil, nil
	}
	return nil, nil, err
}
func projectEvaluationConcern(requirement Requirement, input any, observed bool) (any, error) {
	if missingValue(input) {
		return input, nil
	}
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return nil, err
	}
	projection, err := ProjectConcern(requirement.Kind, fragment, observed, requirement.Constraint != nil)
	if err != nil {
		return nil, err
	}
	return projection.Document(), nil
}
func projectedConstraintsRejected(requirement Requirement, expected, observed any, honoured bool) (bool, error) {
	if requirement.Constraint != nil {
		admitted, err := constraintAdmitsValue(requirement.Constraint, observed)
		return !admitted, err
	}
	if requirement.Structure != nil && !legacyStructureMatches(requirement.Structure.Document(), expected, observed, 0) {
		return true, nil
	}
	if observationKind(requirement.Kind) == termOperatingSystem && *requirement.Posture == termConstrained && requirement.ValueDomain != nil {
		admitted, err := domainAdmitsValue(requirement.ValueDomain, observed)
		if err != nil || !admitted {
			return !admitted, err
		}
	}
	return *requirement.Posture == termExact && !honoured, nil
}
func constraintAdmitsValue(constraint admission.Fragment, input any) (bool, error) {
	if missingValue(input) {
		return false, nil
	}
	owner, err := realizationOwner()
	if err != nil {
		return false, err
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return false, err
	}
	result, err := admission.EvaluateRealizationConstraint(constraint, fragment, admission.DefaultConstraintLimits())
	if err != nil {
		return false, err
	}
	return ownedProjection[map[string]any](result.Document())["status"] == termConformant, nil
}
func domainAdmitsValue(domain admission.Fragment, input any) (bool, error) {
	owner, err := realizationOwner()
	if err != nil {
		return false, err
	}
	document := map[string]any{"semantic_profile": "raes/runtime-value-domain/v1", "default_closure": map[string]any{"posture": "closed", "universe": "runtime-value", "profile": "raes/runtime-value-domain/v1"}, "root": map[string]any{"kind": "domain", "domain": domain.Document()}}
	constraint, err := admission.AdmitFragment(owner, admission.RealizationConstraint, document, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return false, err
	}
	return constraintAdmitsValue(constraint, input)
}
func (s *evaluationState) corroborationDiagnostic(requirement Requirement) *diagnostic.Diagnostic {
	observation, present := s.observation(requirement)
	if observationKind(requirement.Kind) == termOperatingSystem && present && !s.operatingSystemObservationBound(observation) {
		return corroborationFailure(requirement)
	}
	if requirement.ObservationScope == "" && requirement.ObservationStrength == "" {
		return nil
	}
	if present && observationSatisfied(observation.Scope, observation.Strength, requirement.ObservationScope, requirement.ObservationStrength) && s.manifestCorroborates(requirement, observation) {
		return nil
	}
	return corroborationFailure(requirement)
}
func corroborationFailure(requirement Requirement) *diagnostic.Diagnostic {
	return supportFinding(requirement, "runtime.backend-contract-invalid", "Backend returned no valid effective corroboration for '"+requirement.Kind+"' requirement at '"+requirement.FieldPath+"'; matching inventory values alone do not establish realization (SEM-218 I2).")
}
func (s *evaluationState) supportDeclarations(requirement Requirement) []supportDeclaration {
	if declarations, known := s.declarations[requirement.Domain]; known {
		return declarations
	}
	if s.options.Manifest == nil {
		return nil
	}
	declarations, err := declaredSupport(*s.options.Manifest, requirement.Domain)
	// The complete manifest already passed native admission. A broken private
	// projection is an implementation invariant, never a backend-facing value.
	if err != nil {
		panic("realization: invalid owned support declaration")
	}
	s.declarations[requirement.Domain] = declarations
	return declarations
}
func observationPostureSupported(requirement Requirement, declaration supportDeclaration) bool {
	posture := termExact
	if requirement.Posture != nil {
		posture = *requirement.Posture
	}
	switch posture {
	case termOpen:
		if requirement.Kind == termComputeSubstrate {
			return containsString(declaration.constraints, requirement.Kind)
		}
		return declaration.mode == termOpenRealization
	case termConstrained:
		return containsString(declaration.constraints, requirement.Kind)
	default:
		return containsString(declaration.exact, "declared-capability-match")
	}
}
func (s *evaluationState) manifestCorroborates(requirement Requirement, observation evaluatedObservation) bool {
	for _, declaration := range s.supportDeclarations(requirement) {
		capability, present := declaration.observations[observationKind(requirement.Kind)]
		if present && observationPostureSupported(requirement, declaration) && observationSatisfied(capability.scope, capability.strength, observation.Scope, observation.Strength) {
			return true
		}
	}
	return false
}
func containsString(values []string, value string) bool { return slices.Contains(values, value) }

package realization

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

func plannedFragmentLimits() ingress.Limits { return ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128} }

func (s *evaluationState) plannedRequirements() ([]Requirement, error) {
	if !s.plannedViewsReady {
		s.plannedViews, s.plannedViewError = s.recoverPlannedRequirements()
		s.plannedViewsReady = true
	}
	return s.plannedViews, s.plannedViewError
}
func (s *evaluationState) recoverPlannedRequirements() ([]Requirement, error) {
	result := []Requirement{}
	for _, authority := range s.plan.Authority {
		if authority.Mode == termClosed {
			continue
		}
		requirement, err := s.plannedRequirement(authority)
		if err != nil {
			return nil, err
		}
		result = append(result, requirement)
	}
	if err := checkRequirementBatch(result); err != nil {
		return nil, err
	}
	return result, nil
}

func (s *evaluationState) plannedRequirement(authority plannedAuthority) (Requirement, error) {
	provenance := authority.Provenance
	if provenance == "" {
		provenance = termAuthorDeclared
	}
	requirement := Requirement{Address: authority.Address, FieldPath: authority.FieldPath, Domain: authority.Domain, Kind: authority.Kind, Posture: new(authority.Mode), Provenance: provenance, GoverningScope: authority.Scope, ObservationScope: authority.Verification, ObservationStrength: authority.Strength, ConstraintBinding: authority.Binding, ValueConstraints: []ValueConstraint{}, ProcessResourceLimits: []ProcessResourceLimit{}}
	var err error
	requirement.Structure, err = plannedNativeFragment(authority.Structure, admission.RealizationStructure)
	if err != nil {
		return Requirement{}, err
	}
	requirement.Constraint, err = plannedNativeFragment(authority.Constraint, admission.RealizationConstraint)
	if err != nil {
		return Requirement{}, err
	}
	if authority.Kind == termProcessResourceLimits {
		if err := s.plannedProcessDemands(authority, &requirement); err != nil {
			return Requirement{}, err
		}
	}
	return requirement, nil
}

func (s *evaluationState) plannedProcessDemands(authority plannedAuthority, requirement *Requirement) error {
	rows, err := s.plannedProcessValues(authority, requirement)
	if err != nil {
		return err
	}
	known := map[string]bool{}
	for _, input := range rows {
		row, ok := input.(map[string]any)
		if !ok {
			return invalidRealization()
		}
		demand, err := plannedProcessDemand(row)
		if err != nil {
			return err
		}
		requirement.ProcessResourceLimits = append(requirement.ProcessResourceLimits, demand)
		known[demand.IdentityDigest] = true
	}
	return plannedProcessBounds(authority, requirement, known)
}
func (s *evaluationState) plannedProcessValues(authority plannedAuthority, requirement *Requirement) ([]any, error) {
	operation, present := s.operations[authority.Address]
	declared := any(missingConcern{})
	if present {
		declared = plannedPointerValue(operation.Payload, authority.Pointer)
	}
	if missingValue(declared) {
		if authority.Mode == termOpen {
			return []any{}, nil
		}
		return nil, invalidRealization()
	}
	// Process capability metadata uses the incumbent canonical process view.
	projected, err := projectEvaluationConcern(Requirement{Kind: requirement.Kind}, declared, false)
	if err != nil {
		return nil, err
	}
	rows, ok := projected.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	return rows, nil
}
func plannedProcessBounds(authority plannedAuthority, requirement *Requirement, known map[string]bool) error {
	for _, bound := range authority.Bounds {
		if !known[bound.Identity] {
			return invalidRealization()
		}
		domain, err := nativeValue(bound.Domain)
		if err != nil {
			return invalidRealization()
		}
		record, ok := domain.(map[string]any)
		if !ok || record[termKind] != termEnum {
			return invalidRealization()
		}
		allowed, err := nativeValueFragment(record["values"])
		if err != nil {
			return err
		}
		requirement.ValueConstraints = append(requirement.ValueConstraints, ValueConstraint{IdentityDigest: bound.Identity, Leaf: strings.TrimPrefix(bound.Pointer, "/"), Parameter: []string{"plan-authority"}, AllowedValues: allowed})
	}
	return nil
}

func plannedProcessDemand(row map[string]any) (ProcessResourceLimit, error) {
	identity, err := projectionDigest(map[string]any{termResource: row[termResource], termSubject: row[termSubject], termScope: row[termScope]})
	if err != nil {
		return ProcessResourceLimit{}, err
	}
	soft, err := nativeValueFragment(row[termSoft])
	if err != nil {
		return ProcessResourceLimit{}, err
	}
	hard, err := nativeValueFragment(row[termHard])
	if err != nil {
		return ProcessResourceLimit{}, err
	}
	return ProcessResourceLimit{IdentityDigest: identity, Resource: ownedProjection[string](row[termResource]), Scope: ownedProjection[string](row[termScope]), Soft: soft, Hard: hard}, nil
}

func (s *evaluationState) plannedConstraintRequirements() ([]Requirement, error) {
	result := make([]Requirement, 0, len(s.plan.Constraints))
	for _, constraint := range s.plan.Constraints {
		domain, err := plannedNativeFragment(constraint.Domain, admission.RealizationValue)
		if err != nil {
			return nil, err
		}
		result = append(result, Requirement{Address: constraint.Address, FieldPath: constraint.FieldPath, Domain: termRuntimeRealization, Kind: constraint.Concern, Posture: new(constraint.Posture), Provenance: termAuthorDeclared, GoverningScope: constraint.Scope, ValueDomain: domain, ConstraintProvenance: constraint.Provenance})
	}
	return result, nil
}

func plannedPointerValue(input any, pointer string) any {
	if pointer == "" {
		return input
	}
	for _, token := range jsonpointer.Tokens(pointer) {
		switch current := input.(type) {
		case map[string]any:
			child, present := current[token]
			if !present {
				return missingConcern{}
			}
			input = child
		case []any:
			index, valid := jsonpointer.ArrayIndex(token, len(current))
			if !valid {
				return missingConcern{}
			}
			input = current[index]
		default:
			return missingConcern{}
		}
	}
	return input
}

type plannedBoundLookup struct {
	input      any
	identities map[string]any
}

func (lookup *plannedBoundLookup) value(bound plannedBound) any {
	target := lookup.input
	if bound.Identity != "" {
		if lookup.identities == nil {
			lookup.index()
		}
		selected, present := lookup.identities[bound.Identity]
		if !present {
			return missingConcern{}
		}
		target = selected
	}
	return plannedPointerValue(target, bound.Pointer)
}
func (lookup *plannedBoundLookup) index() {
	lookup.identities = map[string]any{}
	rows, ok := lookup.input.([]any)
	if !ok {
		return
	}
	for _, row := range rows {
		identity := plannedProcessIdentity(row)
		if identity == "" {
			continue
		}
		if _, present := lookup.identities[identity]; !present {
			lookup.identities[identity] = row
		}
	}
}

func plannedProcessIdentity(input any) string {
	row, ok := input.(map[string]any)
	if !ok {
		return ""
	}
	subject, ok := row[termSubject].(map[string]any)
	_, resourcePresent := row[termResource]
	_, scopePresent := row[termScope]
	if !ok || !resourcePresent || !scopePresent {
		return ""
	}
	selected := map[string]any{}
	for _, key := range []string{termName, "pid", "parent_pid", termCommand, "command_redacted", "role", "user", "group", "working_directory"} {
		value, present := subject[key]
		if !present {
			return ""
		}
		selected[key] = value
	}
	identity, err := projectionDigest(map[string]any{termResource: row[termResource], termScope: row[termScope], termSubject: selected})
	if err != nil {
		return ""
	}
	return identity
}

func (lookup *plannedBoundLookup) admits(bound plannedBound) (bool, error) {
	value := lookup.value(bound)
	if missingValue(value) {
		return false, nil
	}
	domain, err := plannedNativeFragment(bound.Domain, admission.RealizationValue)
	if err != nil {
		return false, err
	}
	return domainAdmitsValue(domain, value)
}

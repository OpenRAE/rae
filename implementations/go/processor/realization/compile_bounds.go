package realization

import (
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func (s *realizationSource) compileComputeSubstrate(result *Resolution) error {
	for _, name := range s.sections[termNodes].names {
		node := sourceValue(s.model.Nodes)[name]
		if string(sourceValue(node.Type)) == termSwitch {
			continue
		}
		pointer := jsonpointer.FromTokens([]string{termNodes, name})
		posture, scope, origin := termOpen, "#"+pointer, termAuthorDeclared
		requirement := Requirement{FieldPath: "nodes." + name + ".realization.compute-substrate", Domain: termRuntimeRealization, Kind: termComputeSubstrate, Provenance: termAuthorDeclared, ValueConstraints: []ValueConstraint{}, ProcessResourceLimits: []ProcessResourceLimit{}}
		var err error
		requirement.Address, err = address.Render("provision", termNode, name)
		if err != nil {
			return err
		}
		if err := s.substrateBounds(&requirement, pointer, &posture, &origin); err != nil {
			return err
		}

		requirement.Posture = &posture
		requirement.GoverningScope = scope
		requirement.ConstraintProvenance = origin
		result.Requirements = append(result.Requirements, requirement)
	}
	return nil
}

func (s *realizationSource) substrateBounds(requirement *Requirement, pointer string, posture, origin *string) error {
	for _, record := range sourceValue(sourceValue(s.model.InstantiationProvenance).RealizationConstraints) {
		if string(sourceValue(record.Concern)) != termComputeSubstrate || sourceValue(record.FieldPointer) != pointer {
			continue
		}
		*posture, *origin = string(sourceValue(record.Posture)), sourceValue(record.Provenance)
		if raw := sourceValue(record.Domain); len(raw) > 0 {
			value, err := nativeValue(raw)
			if err != nil {
				return err
			}
			requirement.ValueDomain, err = s.valueFragment(value)
			if err != nil {
				return err
			}
		}
	}
	return nil
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func (s *realizationSource) architectureDomain(pointer string) (admission.Fragment, error) {
	constraint, present := s.constraints[pointer]
	if !present {
		return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
	}
	values := []any{}
	seen := map[string]bool{}
	for _, raw := range constraint.Values {
		input, err := nativeValue(raw)
		if err != nil {
			return nil, err
		}
		fragment, err := s.valueFragment(input)
		if err != nil {
			return nil, err
		}
		normalized, err := sdl.NormalizeCapabilityValue("nodes.architecture", fragment)
		if err != nil {
			return nil, err
		}
		value, valid := normalized.Document().(string)
		if !valid {
			return nil, invalidRealization()
		}
		if !seen[value] {
			seen[value] = true
			values = append(values, value)
		}
	}
	return s.valueFragment(map[string]any{termKind: termEnum, termValues: values})
}

func (s *realizationSource) compileBounds(requirement *Requirement, pointer string, value any) error {
	if requirement.Kind == termProcessResourceLimits {
		return s.compileProcessLimits(requirement, pointer, value)
	}
	if requirement.Kind != termOsFamily && requirement.Kind != termOsDistribution && requirement.Kind != termOsVersion {
		return nil
	}
	constraint, present := s.constraints[pointer]
	if !present {
		return nil
	}
	values := make([]any, len(constraint.Values))
	for i, raw := range constraint.Values {
		value, err := nativeValue(raw)
		if err != nil {
			return err
		}
		values[i] = value
	}
	domain, err := s.valueFragment(map[string]any{termKind: termEnum, termValues: values})
	if err != nil {
		return err
	}
	requirement.ValueDomain = domain
	requirement.ConstraintProvenance = "variable-allowed-values"
	return nil
}

func (s *realizationSource) compileProcessLimits(requirement *Requirement, pointer string, value any) error {
	items, ok := value.([]any)
	if !ok {
		return nil
	}
	for index, item := range items {
		demand, err := nativeProcessDemand(item)
		if err != nil {
			return err
		}
		requirement.ProcessResourceLimits = append(requirement.ProcessResourceLimits, demand)
		identity := demand.IdentityDigest

		if err := s.compileProcessLeafBounds(requirement, pointer, index, identity); err != nil {
			return err
		}
	}
	return nil
}

func (s *realizationSource) compileProcessLeafBounds(requirement *Requirement, pointer string, index int, identity string) error {
	for _, leaf := range []string{termSoft, termHard} {
		constraint, exists := s.constraints[pointer+"/"+strconv.Itoa(index)+"/"+leaf]
		if !exists {
			continue
		}
		values := make([]any, len(constraint.Values))
		for i, raw := range constraint.Values {
			value, err := nativeValue(raw)
			if err != nil {
				return err
			}
			values[i] = value
		}
		fragment, err := s.valueFragment(values)
		if err != nil {
			return err
		}
		requirement.ValueConstraints = append(requirement.ValueConstraints, ValueConstraint{IdentityDigest: identity, Leaf: leaf, Parameter: append([]string{}, constraint.Parameter...), AllowedValues: fragment})
	}
	return nil
}

func nativeProcessDemand(item any) (ProcessResourceLimit, error) {
	projection, err := sharedProcessProjection(item, true)
	if err != nil {
		return ProcessResourceLimit{}, err
	}
	identity, err := projectionDigest(map[string]any{termResource: projection[termResource], termScope: projection[termScope], termSubject: projection[termSubject]})
	if err != nil {
		return ProcessResourceLimit{}, err
	}
	soft, err := nativeValueFragment(projection[termSoft])
	if err != nil {
		return ProcessResourceLimit{}, err
	}
	hard, err := nativeValueFragment(projection[termHard])
	if err != nil {
		return ProcessResourceLimit{}, err
	}
	return ProcessResourceLimit{IdentityDigest: identity, Resource: ownedProjection[string](projection[termResource]), Scope: ownedProjection[string](projection[termScope]), Soft: soft, Hard: hard}, nil
}

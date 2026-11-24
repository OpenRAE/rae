package realization

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

// AdmitRequirement bounds and checks caller-supplied typed requirements through
// the shared compiled requirement model. It grants no execution authority.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func AdmitRequirement(requirement Requirement) (admission.Fragment, error) {
	if err := checkRequirementFragments(requirement); err != nil {
		return nil, err
	}
	document := map[string]any{"field_path": requirement.FieldPath, termAddress: requirement.Address, termDomain: requirement.Domain, "requirement_kind": requirement.Kind, "explicitness": nil, termProvenance: requirement.Provenance, termGoverningScope: optionalText(requirement.GoverningScope), "delegated": requirement.Delegated, "artifact_requirement": nil, "verification_scope": optionalText(requirement.ObservationScope), "required_observation_strength": optionalText(requirement.ObservationStrength), "value_domain": fragmentDocument(requirement.ValueDomain), "constraint_provenance": optionalText(requirement.ConstraintProvenance), "structure": fragmentDocument(requirement.Structure), "constraint_document": fragmentDocument(requirement.Constraint), "constraint_binding": optionalText(requirement.ConstraintBinding), "structure_error": requirement.StructureError, "recursive_pending": requirement.RecursivePending}
	if requirement.Posture != nil {
		document["explicitness"] = *requirement.Posture
	}
	constraints := make([]any, len(requirement.ValueConstraints))
	for index, constraint := range requirement.ValueConstraints {
		constraints[index] = map[string]any{"identity_digest": constraint.IdentityDigest, "leaf": constraint.Leaf, "parameter": stringValues(constraint.Parameter), "allowed_values": constraint.AllowedValues.Document()}
	}
	document["value_constraints"] = constraints
	limits := make([]any, len(requirement.ProcessResourceLimits))
	for index, limit := range requirement.ProcessResourceLimits {
		limits[index] = map[string]any{"identity_digest": limit.IdentityDigest, termResource: limit.Resource, termScope: limit.Scope, termSoft: limit.Soft.Document(), termHard: limit.Hard.Document()}
	}
	document["process_resource_limits"] = limits
	if requirement.ArtifactRequirement != nil {
		artifact, err := requirementArtifactProjection(requirement.ArtifactRequirement)
		if err != nil {
			return nil, err
		}
		document["artifact_requirement"] = artifact
	}
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(owner, admission.CompiledRealizationRequirement, document, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 256})
}

func checkRequirementFragments(requirement Requirement) error {
	if len(requirement.ValueConstraints) > 16384 || len(requirement.ProcessResourceLimits) > 16384 {
		return invalidRealization()
	}
	fragments := []struct {
		value   admission.Fragment
		profile admission.FragmentProfile
	}{{requirement.ValueDomain, admission.RealizationValue}, {requirement.Constraint, admission.RealizationConstraint}, {requirement.Structure, admission.RealizationStructure}}
	for _, fragment := range fragments {
		if fragment.value != nil && admission.CheckFragment(fragment.value, fragment.profile) != nil {
			return invalidRealization()
		}
	}
	for _, constraint := range requirement.ValueConstraints {
		if len(constraint.Parameter) > 32 || admission.CheckFragment(constraint.AllowedValues, admission.RealizationValue) != nil {
			return invalidRealization()
		}
	}
	for _, limit := range requirement.ProcessResourceLimits {
		if admission.CheckFragment(limit.Soft, admission.RealizationValue) != nil || admission.CheckFragment(limit.Hard, admission.RealizationValue) != nil {
			return invalidRealization()
		}
	}
	return nil
}
func requirementArtifactProjection(input *binding.ArtifactRequirementV1) (any, error) {
	if admission.CheckTransport(input, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}) != nil {
		return nil, invalidRealization()
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, invalidRealization()
	}
	var portable struct {
		Source struct {
			Requirement json.RawMessage `json:"artifact_requirement"`
		} `json:"source"`
	}
	if json.Unmarshal(raw, &portable) != nil || len(portable.Source.Requirement) == 0 {
		return nil, invalidRealization()
	}
	value, err := nativeValue(portable.Source.Requirement)
	if err != nil {
		return nil, invalidRealization()
	}
	return value, nil
}

func optionalText(text string) any {
	if text == "" {
		return nil
	}
	return text
}
func fragmentDocument(input admission.Fragment) any {
	if input == nil {
		return nil
	}
	return input.Document()
}

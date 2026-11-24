package realization

import (
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// SelectionAdmits checks a backend candidate against its authored authority.
// The candidate follows the closed observation shape; admission makes no claim
// that a backend has delivered or independently observed the selected value.
func SelectionAdmits(requirement Requirement, expected, actual admission.Fragment) (bool, error) {
	if admission.CheckFragment(expected, admission.RealizationValue) != nil || admission.CheckFragment(actual, admission.RealizationValue) != nil {
		return false, invalidRealization()
	}
	if _, err := AdmitRequirement(requirement); err != nil {
		return false, err
	}
	if requirement.StructureError {
		return false, nil
	}
	before, after := expected.Document(), actual.Document()
	if requirement.Kind != termComputeSubstrate {
		var err error
		before, err = projectEvaluationConcern(requirement, before, false)
		if err != nil {
			return selectionProjectionFailure(err)
		}
		after, err = projectEvaluationConcern(requirement, after, true)
		if err != nil {
			return selectionProjectionFailure(err)
		}
	}
	return selectedProjectionAdmits(requirement, before, after)
}
func selectedProjectionAdmits(requirement Requirement, before, after any) (bool, error) {
	if requirement.ValueDomain != nil {
		admitted, err := domainAdmitsValue(requirement.ValueDomain, after)
		if err != nil || !admitted {
			return admitted, err
		}
	}
	if requirement.Constraint != nil {
		return constraintAdmitsValue(requirement.Constraint, after)
	}
	if requirement.Structure != nil {
		return legacyStructureMatches(requirement.Structure.Document(), before, after, 0), nil
	}
	if requirement.Posture != nil && (*requirement.Posture == termOpen || *requirement.Posture == termConstrained) {
		return true, nil
	}
	return projectionEqual(before, after, true), nil
}
func selectionProjectionFailure(err error) (bool, error) {
	if category, _ := fault.CategoryOf(err); category == fault.InvalidInput {
		return false, nil
	}
	return false, err
}

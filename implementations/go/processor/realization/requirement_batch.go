package realization

import "github.com/OpenRAE/rae/implementations/go/internal/base/value"

// A public requirement slice remains bounded as one input, even when every
// member separately fits its native model. The closed projection invokes no
// foreign fragment method: AdmitRequirement checks its carriers first.
func checkRequirementBatch(requirements []Requirement) error {
	if len(requirements) > 16384 {
		return invalidRealization()
	}
	return value.ValidateProjected(requirements, value.Plan(), requirementBatchValue)
}
func requirementBatchValue(input any) (any, error) {
	switch entry := input.(type) {
	case []Requirement:
		result := make([]any, len(entry))
		for index := range entry {
			result[index] = &entry[index]
		}
		return result, nil
	case *Requirement:
		if entry == nil {
			return nil, invalidRealization()
		}
		fragment, err := AdmitRequirement(*entry)
		if err != nil {
			return nil, err
		}
		return fragment.Document(), nil
	default:
		return input, nil
	}
}

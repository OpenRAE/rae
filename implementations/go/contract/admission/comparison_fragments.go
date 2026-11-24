package admission

import "github.com/OpenRAE/rae/implementations/go/base/ingress"

func comparisonCoordinateFragment(v *Validator, data []byte, limits ingress.Limits) error {
	const contract = "semantic-comparison-request-v1"
	const pointer = "#/properties/before"
	if err := v.checkModelFragment(contract, pointer, data, limits); err != nil {
		return err
	}
	normalized, err := v.low.DefaultedObjectFragment(contract, pointer, data, limits)
	if err != nil {
		return err
	}
	return comparisonCoordinate(normalized)
}
func comparisonImpactScopeFragment(v *Validator, data []byte, limits ingress.Limits) error {
	const contract = "semantic-comparison-request-v1"
	const pointer = "#/$defs/ImpactScopeModel"
	if err := v.checkModelFragment(contract, pointer, data, limits); err != nil {
		return err
	}
	normalized, err := v.low.DefaultedObjectFragment(contract, pointer, data, limits)
	if err != nil {
		return err
	}
	return comparisonImpactScope(normalized)
}

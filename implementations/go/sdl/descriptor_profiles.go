package sdl

import "github.com/OpenRAE/rae/implementations/go/contract/binding"

// DescriptorProfiles projects only bindings admitted by the native SDL owner.
func DescriptorProfiles(scenario Scenario) ([]binding.DomainProfileBindingV1, error) {
	input, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	return input.document.DescriptorProfiles()
}

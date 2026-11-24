package sdl

import "github.com/OpenRAE/rae/implementations/go/contract/admission"

// EvidenceScenario binds an admitted authored scenario to its native canonical
// digest for evidence relations. Concrete and foreign handles are refused.
func EvidenceScenario(input Scenario) (admission.EvidenceScenario, error) {
	scenario, err := nativeScenario(input)
	if err != nil {
		return admission.EvidenceScenario{}, err
	}
	return scenario.parser.EvidenceScenario(scenario.document)
}

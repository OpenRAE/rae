package sdl

import (
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// EnvelopeMembershipDiagnostics compares an exact admitted instantiated
// scenario with its configured offer through native model presence.
func EnvelopeMembershipDiagnostics(input InstantiatedScenario, envelope binding.RealizationEnvelopeV1) ([]diagnostic.Diagnostic, error) {
	owned, ok := input.(*instantiated)
	if !ok || owned == nil || owned.scenario == nil || owned.parser == nil || owned.document == nil {
		return nil, invalidScenario()
	}
	return owned.parser.EnvelopeMembershipDiagnostics(owned.document, envelope)
}

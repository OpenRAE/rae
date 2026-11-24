package sdl

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

// ValidateNodeRealizationContext checks native platform, infrastructure,
// runtime and stateful references. It returns no admitted scenario or intent.
func ValidateNodeRealizationContext(input admission.Fragment) ([]diagnostic.Diagnostic, error) {
	if err := admission.CheckFragment(input, admission.RealizationValue); err != nil {
		return nil, err
	}
	raw, err := json.Marshal(input.Document())
	if err != nil {
		return nil, err
	}
	parser, err := scenarioParser(DefaultLimits())
	if err != nil {
		return nil, err
	}
	return parser.ValidateNodeRealizationContext(raw)
}

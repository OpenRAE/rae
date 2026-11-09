package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
)

func temporalSource(invocation validation.Invocation) error {
	data, err := json.Marshal(sdlInstance(invocation))
	if err != nil {
		return invalid()
	}
	findings, err := sdlrules.TemporalBindings(data, nil)
	if err != nil || len(findings) != 0 {
		return invalid()
	}
	return nil
}

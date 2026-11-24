package governance

import (
	"encoding/json"
	"math"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// validateContract composes the canonical schema and model-semantic owners.
// It never replaces semantic admission with generic JSON Schema validation.
func (c *checker) validateContract(id string, data []byte) (validation.Value, error) {
	if c.contracts == nil {
		validator, err := admission.New()
		if err != nil {
			return validation.Value{}, err
		}
		c.contracts = validator
	}
	// These reference readers have no byte ceiling. Default annotations may
	// enlarge a model, so the admission budget must not equal its input length.
	return c.contracts.Validate(id, data, ingress.Limits{MaxBytes: math.MaxInt, MaxDepth: 65000}, nil)
}

func canonicalJSON(value any, ascii bool) ([]byte, error) {
	data, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	return canonjson.Sorted(data, ascii)
}

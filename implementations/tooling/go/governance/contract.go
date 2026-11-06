package governance

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// validateContract composes the canonical schema and model-semantic owners.
// It never replaces semantic admission with generic JSON Schema validation.
func validateContract(id string, data []byte) (validation.Value, error) {
	v, err := admission.New()
	if err != nil {
		return validation.Value{}, err
	}
	return v.Validate(id, data, ingress.Limits{MaxBytes: max(1, len(data)), MaxDepth: 65000}, nil)
}

func canonicalJSON(value any) ([]byte, error) {
	data, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	return canonjson.Sorted(data, false)
}

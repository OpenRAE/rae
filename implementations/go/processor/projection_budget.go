package processor

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// Only the external document boundary uses these shallow wire views. Compiler
// stages retain typed records and the shared value owner consumes the budget.
func compiledProjectionValue(input any) (any, error) {
	switch item := input.(type) {
	case json.RawMessage:
		return compiledRawValue(item)
	case []json.RawMessage:
		return compiledSequence(item)
	case []string:
		return compiledSequence(item)
	case []Scalar:
		return compiledSequence(item)
	case []map[string]any:
		return compiledSequence(item)
	case []binding.DomainProfileBindingV1:
		return compiledSequence(item)
	case map[string]json.RawMessage:
		return compiledMapping(item)
	case map[string][]any:
		return compiledMapping(item)
	default:
		return compiledLeafProjection(input)
	}
}
func compiledLeafProjection(input any) (any, error) {
	switch item := input.(type) {
	case compiledResourceWire:
		return compiledResourceProjection(Resource(item))
	case *string:
		var result any
		if item != nil {
			result = *item
		}
		return result, nil
	case *json.Number:
		var result any
		if item != nil {
			result = *item
		}
		return result, nil
	case Scalar:
		if item.kind == "" {
			return nil, invalidCompiled()
		}
		return item.value, nil
	case binding.DomainProfileBindingV1:
		return compiledGeneratedValue(item)
	case *binding.PlanRealizationProfilesV1:
		var result any
		if item == nil {
			return result, nil
		}
		return compiledGeneratedValue(item)
	default:
		return input, nil // The shared walker refuses every unknown carrier.
	}
}
func compiledSequence[T any](input []T) ([]any, error) {
	if input == nil {
		return []any(nil), nil
	}
	if len(input) > value.Plan().MaxMembers {
		return nil, value.ErrLimit
	}
	result := make([]any, len(input))
	for i, item := range input {
		result[i] = item
	}
	return result, nil
}
func compiledMapping[T any](input map[string]T) (any, error) {
	if len(input) > value.Plan().MaxMembers {
		return nil, value.ErrLimit
	}
	result := make(map[string]any, len(input))
	for key, item := range input {
		result[key] = item
	}
	return result, nil
}
func compiledRawValue(raw []byte) (any, error) {
	var result any
	if len(raw) == 0 {
		return result, nil
	}
	if len(raw) > 8<<20 {
		return nil, value.ErrLimit
	}
	parsed, err := ingress.Parse(append(append([]byte{'['}, raw...), ']'), ingress.Limits{MaxBytes: len(raw) + 2, MaxDepth: value.Plan().MaxDepth + 1}, ingress.Array)
	if err != nil {
		return nil, err
	}
	sequence, ok := parsed.([]any)
	if !ok || len(sequence) != 1 {
		return nil, value.ErrInput
	}
	return sequence[0], nil
}
func compiledGeneratedValue(input any) (any, error) {
	if err := admission.CheckTransport(input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}); err != nil {
		return nil, err
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, err
	}
	return compiledRawValue(raw)
}

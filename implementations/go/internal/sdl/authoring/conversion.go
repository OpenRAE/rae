package authoring

import (
	"encoding/json"
	"math/big"
	"slices"
	"strings"
)

type scalarPolicy struct {
	Minimum *string       `json:"minimum"`
	Maximum *string       `json:"maximum"`
	Shapes  []string      `json:"shapes"`
	Convert []string      `json:"convert"`
	Items   *scalarPolicy `json:"items"`
	Values  *scalarPolicy `json:"values"`
}

func childPolicy(policy *scalarPolicy) scalarPolicy {
	if policy == nil {
		return scalarPolicy{}
	}
	return *policy
}
func (w *normalizer) convert(schema map[string]any, value any, policy scalarPolicy) (any, error) {
	if len(policy.Convert) > 0 {
		for _, operation := range policy.Convert {
			var err error
			value, err = w.operation(schema, value, operation)
			if err != nil {
				return nil, err
			}
		}
	}
	value, err := coerceScalar(value, policy.Shapes)
	if err != nil {
		return nil, err
	}
	if err = scalarBounds(value, policy); err != nil {
		return nil, err
	}
	return value, nil
}
func (w *normalizer) operation(schema map[string]any, value any, operation string) (any, error) {
	if operation == "strings" {
		if value == nil {
			return []any{}, nil
		}
		if s, ok := value.(string); ok {
			return []any{s}, nil
		}
		return value, nil
	}
	if value == nil || variable(value) {
		return value, nil
	}
	switch v := value.(type) {
	case []any:
		out := make([]any, len(v))
		for i, raw := range v {
			converted, err := w.operation(object(schema["items"]), raw, operation)
			if err != nil {
				return nil, err
			}
			out[i] = converted
		}
		return out, nil
	case map[string]any:
		if operation != "duration" {
			return value, nil
		}
		out := map[string]any{}
		for name, raw := range v {
			converted, err := duration(raw)
			if err != nil {
				return nil, err
			}
			out[name] = converted
		}
		return out, nil
	}
	return w.scalarOperation(schema, value, operation)
}
func (w *normalizer) scalarOperation(schema map[string]any, value any, operation string) (any, error) {
	switch operation {
	case "normalize":
		if s, ok := value.(string); ok {
			return strings.ReplaceAll(strings.ToLower(s), "-", "_"), nil
		}
		return value, nil
	case "enum", "vocabulary":
		return w.enum(schema, value, operation == "vocabulary")
	case "integer":
		return normalizeInteger(value, true)
	case "number":
		return normalizeFloat(value)
	case "boolean":
		return normalizeBoolean(value, true)
	case "ram":
		return ram(value)
	case "duration":
		return duration(value)
	case "architecture":
		return architecture(value), nil
	case "distribution":
		if s, ok := value.(string); ok {
			return strings.ToLower(s), nil
		}
		return nil, invalid()
	case "os-version":
		return value, nil // The published token constraints apply unchanged.
	case "limit":
		if value == "unlimited" {
			return value, nil
		}
		return normalizeInteger(value, true)
	default:
		return nil, invalid()
	}
}
func (w *normalizer) enum(schema map[string]any, value any, extension bool) (any, error) {
	s, ok := value.(string)
	if !ok {
		return nil, invalid()
	}
	if extension && strings.HasPrefix(s, "x-") {
		return s, nil
	} // Exact identity is checked by the contract owner.
	return normalizeEnum(value, w.enumMembers(schema, 0))
}
func (w *normalizer) enumMembers(schema map[string]any, depth int) []any {
	if depth > 16 {
		return nil
	}
	schema, _ = w.dereference(schema, "")
	result := append([]any(nil), array(schema["enum"])...)
	for _, raw := range alternatives(schema) {
		result = append(result, w.enumMembers(object(raw), depth+1)...)
	}
	return result
}
func coerceScalar(value any, shapes []string) (any, error) {
	if value == nil || len(shapes) == 0 {
		return value, nil
	}
	if stringShape(value, shapes) || booleanShape(value, shapes) {
		return value, nil
	}
	switch v := value.(type) {
	case map[string]any, []any:
		return value, nil
	case json.Number:
		if slices.Contains(shapes, "integer") || slices.Contains(shapes, "integer!") {
			if _, err := v.Int64(); err == nil || !strings.ContainsAny(v.String(), ".eE") {
				return value, nil
			}
		}
	case float64:
		if slices.Contains(shapes, "number") || slices.Contains(shapes, "number!") {
			return normalizeFloat(v)
		}
	}
	return fallbackScalar(value, shapes)
}
func stringShape(value any, shapes []string) bool {
	_, ok := value.(string)
	return ok && (slices.Contains(shapes, "string") || slices.Contains(shapes, "string!"))
}
func booleanShape(value any, shapes []string) bool {
	_, ok := value.(bool)
	return ok && (slices.Contains(shapes, "boolean") || slices.Contains(shapes, "boolean!"))
}
func fallbackScalar(value any, shapes []string) (any, error) {
	if slices.Contains(shapes, "integer") {
		return normalizeInteger(value, false)
	}
	if slices.Contains(shapes, "number") {
		if boolean, ok := value.(bool); ok {
			if boolean {
				return json.Number("1.0"), nil
			}
			return json.Number("0.0"), nil
		}
		return normalizeFloat(value)
	}
	if slices.Contains(shapes, "number!") {
		if _, ok := value.(json.Number); ok {
			return normalizeFloat(value)
		}
	}
	if slices.Contains(shapes, "boolean") {
		return normalizeBoolean(value, false)
	}
	// Strict fields must reject before JSON numeric equivalence can erase their source type.
	if slices.Contains(shapes, "integer!") || slices.Contains(shapes, "number!") {
		return nil, invalid()
	}
	return value, nil
}

func scalarBounds(value any, policy scalarPolicy) error {
	if policy.Minimum == nil && policy.Maximum == nil {
		return nil
	}
	switch v := value.(type) {
	case []any:
		for _, item := range v {
			if err := scalarBounds(item, policy); err != nil {
				return err
			}
		}
		return nil
	case map[string]any:
		for _, item := range v {
			if err := scalarBounds(item, policy); err != nil {
				return err
			}
		}
		return nil
	}
	n, ok := value.(json.Number)
	if !ok {
		return nil
	}
	number, valid := new(big.Rat).SetString(n.String())
	if !valid {
		return invalid()
	}
	if policy.Minimum != nil {
		bound, ok := new(big.Rat).SetString(*policy.Minimum)
		if !ok || number.Cmp(bound) < 0 {
			return invalid()
		}
	}
	if policy.Maximum != nil {
		bound, ok := new(big.Rat).SetString(*policy.Maximum)
		if !ok || number.Cmp(bound) > 0 {
			return invalid()
		}
	}
	return nil
}

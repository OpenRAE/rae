package authoring

import (
	"encoding/json"
	"math/big"
	"regexp"
	"slices"
	"strings"
)

type scalarPolicy struct {
	Members []string      `json:"members"`
	Scopes  []string      `json:"scopes"`
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
			value, err = w.operation(schema, value, operation, policy)
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
func (w *normalizer) operation(schema map[string]any, value any, operation string, policy scalarPolicy) (any, error) {
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
		return w.sequenceOperation(schema, v, operation, policy)
	case map[string]any:
		if operation != "duration" {
			return value, nil
		}
		return durationMap(v)
	}
	return w.scalarOperation(schema, value, operation, policy)
}
func (w *normalizer) sequenceOperation(schema map[string]any, values []any, operation string, policy scalarPolicy) (any, error) {
	result := make([]any, len(values))
	for i, raw := range values {
		value, err := w.operation(object(schema["items"]), raw, operation, policy)
		if err != nil {
			return nil, err
		}
		result[i] = value
	}
	return result, nil
}
func durationMap(values map[string]any) (any, error) {
	result := make(map[string]any, len(values))
	for name, raw := range values {
		value, err := duration(raw)
		if err != nil {
			return nil, err
		}
		result[name] = value
	}
	return result, nil
}
func (w *normalizer) scalarOperation(schema map[string]any, value any, operation string, policy scalarPolicy) (any, error) {
	switch operation {
	case "normalize":
		if s, ok := value.(string); ok {
			return w.caseText(s, true)
		}
		return value, nil
	case "account-vocabulary":
		return w.accountVocabulary(value, policy)
	case "capability":
		return w.capability(value)
	case "enum", "vocabulary":
		return w.enum(schema, value, operation == "vocabulary", policy)
	case integerType:
		return normalizeInteger(value, true)
	case numberType:
		return normalizeFloat(value)
	case booleanType:
		return normalizeBoolean(value, true)
	case "ram":
		return ram(value)
	case "duration":
		return duration(value)
	case architectureField, "distribution":
		return w.platformToken(value, operation)
	case "os-version":
		if s, ok := value.(string); !ok || !osReleaseToken.MatchString(s) {
			return nil, invalid()
		}
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
func (w *normalizer) enum(schema map[string]any, value any, extension bool, policy scalarPolicy) (any, error) {
	s, ok := value.(string)
	if !ok {
		return nil, invalid()
	}
	members := make([]any, 0, len(policy.Members))
	for _, member := range policy.Members {
		members = append(members, member)
	}
	if len(members) == 0 {
		members = w.enumMembers(schema, 0)
	}
	cased, err := w.caseText(s, true)
	if err != nil {
		return nil, err
	}
	if normalized, err := normalizeEnum(cased, members); err == nil {
		return normalized, nil
	}
	if extension {
		for _, scope := range policy.Scopes {
			if w.parser.authority.CheckScope(scope, s) == nil {
				return s, nil
			}
		}
	}
	return nil, invalid()
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
		if slices.Contains(shapes, integerType) || slices.Contains(shapes, "integer!") {
			if _, err := v.Int64(); err == nil || !strings.ContainsAny(v.String(), ".eE") {
				return value, nil
			}
		}
	case float64:
		if slices.Contains(shapes, numberType) || slices.Contains(shapes, "number!") {
			return normalizeFloat(v)
		}
	}
	return fallbackScalar(value, shapes)
}
func stringShape(value any, shapes []string) bool {
	_, ok := value.(string)
	return ok && (slices.Contains(shapes, stringType) || slices.Contains(shapes, "string!"))
}
func booleanShape(value any, shapes []string) bool {
	_, ok := value.(bool)
	return ok && (slices.Contains(shapes, booleanType) || slices.Contains(shapes, "boolean!"))
}
func fallbackScalar(value any, shapes []string) (any, error) {
	if slices.Contains(shapes, integerType) {
		return normalizeInteger(value, false)
	}
	if slices.Contains(shapes, numberType) {
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
	if slices.Contains(shapes, booleanType) {
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
	return scalarNumberBounds(value, policy)
}
func scalarNumberBounds(value any, policy scalarPolicy) error {
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

var (
	accountExtension = regexp.MustCompile(`^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*\z`)
	osReleaseToken   = regexp.MustCompile(`^(?:[!-~](?:[ -~]{0,126}[!-~])?)?\z`)
)

func (w *normalizer) accountVocabulary(value any, policy scalarPolicy) (any, error) {
	text, ok := value.(string)
	if !ok {
		return nil, invalid()
	}
	normalized, err := w.caseText(text, true)
	if err != nil {
		return nil, err
	}
	if slices.Contains(policy.Members, normalized) {
		return normalized, nil
	}
	extension, err := w.caseText(text, false)
	if err != nil {
		return nil, err
	}
	if accountExtension.MatchString(extension) {
		return extension, nil
	}
	return nil, invalid()
}

func (w *normalizer) platformToken(value any, operation string) (any, error) {
	s, ok := value.(string)
	if ok && strings.ContainsAny(s, "\r\n") {
		return nil, invalid()
	}
	if operation == architectureField {
		if !ok {
			return architecture(value), nil
		}
		cased, err := w.caseText(s, false)
		if err != nil {
			return nil, err
		}
		return architecture(cased), nil
	}
	if !ok {
		return nil, invalid()
	}
	return w.caseText(s, false)
}

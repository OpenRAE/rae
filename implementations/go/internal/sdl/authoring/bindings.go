package authoring

import (
	"encoding/json"
	"math"
	"math/big"
	"strconv"

	"strings"
)

type substitution struct {
	keepUnknown bool
	values      map[string]any
	preserved   map[string]bool
	copies      *copyBudget
	inline      map[string]string
}

func (c *composition) bind(value, decl, descriptor map[string]any) (map[string]any, error) {
	variables := object(value[variablesSection])
	s := substitution{values: map[string]any{}, preserved: preservedVariables(value), copies: &c.copies, inline: map[string]string{}}
	if err := s.resolveValues(variables, object(decl["parameters"]), descriptor); err != nil {
		return nil, err
	}
	content := make(map[string]any, len(value))
	for key, child := range value {
		if key != controlAssetsSection {
			content[key] = child
		}
	}
	substituted, err := s.walk(content)
	if err != nil {
		return nil, err
	}
	result := object(substituted)
	if pinned, present := value[controlAssetsSection]; present {
		result[controlAssetsSection] = pinned
	}
	if err = authoredReferences(result, value); err != nil {
		return nil, err
	}
	kept := map[string]any{}
	for name, definition := range object(result[variablesSection]) {
		if s.preserved[name] {
			kept[name] = definition
		}
	}
	result[variablesSection] = kept
	delete(result, "module")
	delete(result, "realization")
	return c.validateBound(result)
}
func preservedVariables(value map[string]any) map[string]bool {
	result := map[string]bool{}
	for _, raw := range object(value[variationPointsField]) {
		point := object(raw)
		if point["kind"] == "parameter" {
			result[text(object(point[targetField])["variable"])] = true
		}
	}
	return result
}
func (s *substitution) resolveValues(variables, parameters, descriptor map[string]any) error {
	allowed := map[string]bool{}
	for _, name := range array(descriptor["parameters"]) {
		allowed[text(name)] = true
	}
	for name := range parameters {
		if !allowed[name] || variables[name] == nil || s.preserved[name] {
			return importError(parameterRefusedCode)
		}
	}
	for name, raw := range variables {
		if s.preserved[name] {
			continue
		}
		definition := object(raw)
		candidate, present, err := bindingCandidate(name, definition, parameters)
		if err != nil {
			return err
		}
		if !present {
			continue
		}
		s.values[name] = candidate
	}
	return nil
}
func bindingCandidate(name string, definition, parameters map[string]any) (any, bool, error) {
	candidate, present := parameters[name]
	if !present {
		candidate = definition[defaultField]
		present = candidate != nil
	}
	if !present {
		if definition["required"] == true {
			return nil, false, importError(parameterRefusedCode)
		}
		return nil, false, nil
	}
	if !variableType(candidate, text(definition["type"])) || !allowedValue(candidate, array(definition["allowed_values"])) {
		return nil, false, importError(parameterRefusedCode)
	}
	return candidate, true, nil
}
func variableType(value any, kind string) bool {
	switch kind {
	case stringType:
		_, ok := value.(string)
		return ok
	case booleanType:
		_, ok := value.(bool)
		return ok
	case integerType:
		n, ok := value.(json.Number)
		if !ok {
			return false
		}
		_, ok = new(big.Int).SetString(n.String(), 10)
		return ok
	case numberType:
		switch value.(type) {
		case json.Number, float64:
			return true
		default:
			return false
		}
	default:
		return false
	}
}
func allowedValue(value any, allowed []any) bool {
	if len(allowed) == 0 {
		return true
	}
	for _, candidate := range allowed {
		if scalarEqual(value, candidate) {
			return true
		}
	}
	return false
}
func (s *substitution) walk(value any) (any, error) {
	switch v := value.(type) {
	case ordered:
		return s.walk(object(v))
	case map[string]any:
		out := make(map[string]any, len(v))
		for key, item := range v {
			replaced, err := s.walk(item)
			if err != nil {
				return nil, err
			}
			out[key] = replaced
		}
		return out, nil
	case []any:
		out := make([]any, len(v))
		for i, item := range v {
			replaced, err := s.walk(item)
			if err != nil {
				return nil, err
			}
			out[i] = replaced
		}
		return out, nil
	case string:
		return s.string(v)
	default:
		return value, nil
	}
}
func (s *substitution) string(value string) (any, error) {
	if variable(value) {
		return s.wholeToken(value)
	}
	if cached, present := s.inline[value]; present {
		return cached, nil
	}
	replaced, err := s.copies.replace(value, s.inlineToken)
	if err != nil {
		return nil, err
	}
	s.inline[value] = replaced
	return replaced, nil
}
func (s *substitution) wholeToken(token string) (any, error) {
	name := token[2 : len(token)-1]
	if s.preserved[name] || (s.keepUnknown && s.values[name] == nil) {
		return token, nil
	}
	replacement, ok := s.values[name]
	if !ok {
		return nil, importError(parameterRefusedCode)
	}
	return replacement, nil
}
func (s *substitution) inlineToken(token, name string) (string, error) {
	if !s.preserved[name] && (!s.keepUnknown || s.values[name] != nil) {
		replacement, ok := s.values[name]
		if !ok {
			return "", importError(parameterRefusedCode)
		}
		token = pythonScalar(replacement)
	}
	return token, nil
}
func pythonScalar(value any) string {
	switch v := value.(type) {
	case string:
		return v
	case bool:
		if v {
			return "True"
		}
		return "False"
	case json.Number:
		if !strings.ContainsAny(v.String(), ".eE") {
			return v.String()
		}
		f, err := v.Float64()
		if err == nil {
			return inlineFloat(f)
		}
	case float64:
		return inlineFloat(v)
	}
	return "None"
}
func inlineFloat(value float64) string {
	format := byte('f')
	absolute := math.Abs(value)
	if absolute != 0 && (absolute < 1e-4 || absolute >= 1e16) {
		format = 'e'
	}
	result := strconv.FormatFloat(value, format, -1, 64)
	if !strings.ContainsAny(result, ".e") {
		result += ".0"
	}
	return result
}
func scalarNumber(value any) (*big.Rat, bool) {
	switch v := value.(type) {
	case json.Number:
		if strings.ContainsAny(v.String(), ".eE") {
			number, err := v.Float64()
			if err != nil {
				return nil, false
			}
			return scalarNumber(number)
		}
		return new(big.Rat).SetString(v.String())
	case float64:
		if n := new(big.Rat).SetFloat64(v); n != nil {
			return n, true
		}
	case bool:
		if v {
			return big.NewRat(1, 1), true
		}
		return big.NewRat(0, 1), true
	}
	return nil, false
}
func scalarEqual(left, right any) bool {
	a, aOK := scalarNumber(left)
	b, bOK := scalarNumber(right)
	if aOK && bOK {
		return a.Cmp(b) == 0
	}
	switch v := left.(type) {
	case string:
		other, ok := right.(string)
		return ok && v == other
	case nil:
		return right == nil
	}
	return false
}

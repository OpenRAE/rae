package authoring

import (
	"encoding/json"
	"math/big"

	"regexp"
	"strings"
)

type substitution struct {
	values    map[string]any
	preserved map[string]bool
	tokens    *regexp.Regexp
	nodes     int
	bytes     int64
}

func (c *composition) bind(value, decl, descriptor map[string]any) (map[string]any, error) {
	variables := object(value["variables"])
	parameters := object(decl["parameters"])
	allowed := map[string]bool{}
	for _, name := range array(descriptor["parameters"]) {
		allowed[text(name)] = true
	}
	for name := range parameters {
		if !allowed[name] || variables[name] == nil {
			return nil, importError("parameter-refused")
		}
	}
	s := substitution{values: map[string]any{}, preserved: map[string]bool{}, tokens: regexp.MustCompile(`\$\{((?:(?:[a-z0-9][a-z0-9_-]{0,63}|__private)\.)*[a-z0-9][a-z0-9_-]{0,63})\}`), nodes: c.parser.limits.MaxComposedNodes, bytes: c.parser.limits.MaxComposedBytes}
	for _, raw := range object(value["variation_points"]) {
		point := object(raw)
		if point["kind"] == "parameter" {
			s.preserved[text(object(point["target"])["variable"])] = true
		}
	}
	for name, raw := range variables {
		definition := object(raw)
		candidate, present := parameters[name]
		if s.preserved[name] {
			if present {
				return nil, importError("parameter-refused")
			}
			continue
		}
		if !present {
			candidate, present = definition["default"]
			present = present && candidate != nil
		}
		if !present {
			if definition["required"] == true {
				return nil, importError("parameter-refused")
			}
			continue
		}
		if !variableType(candidate, text(definition["type"])) || !allowedValue(candidate, array(definition["allowed_values"])) {
			return nil, importError("parameter-refused")
		}
		s.values[name] = candidate
	}
	substituted, err := s.walk(value)
	if err != nil {
		return nil, err
	}
	result := object(substituted)
	kept := map[string]any{}
	for name, definition := range variables {
		if s.preserved[name] {
			kept[name] = definition
		}
	}
	result["variables"] = kept
	// The descriptor belongs to resolution, not the bound content.
	delete(result, "module")
	delete(result, "realization")
	return result, nil
}
func variableType(value any, kind string) bool {
	switch kind {
	case "string":
		_, ok := value.(string)
		return ok
	case "boolean":
		_, ok := value.(bool)
		return ok
	case "integer":
		n, ok := value.(json.Number)
		if !ok {
			return false
		}
		_, ok = new(big.Int).SetString(n.String(), 10)
		return ok
	case "number":
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
	s.nodes--
	if s.nodes < 0 {
		return nil, importError("budget-exceeded")
	}
	switch v := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(v))
		for key, item := range v {
			if key == "control_context_assets" {
				out[key] = item
				continue
			}
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
		name := value[2 : len(value)-1]
		if s.preserved[name] {
			return value, nil
		}
		replacement, ok := s.values[name]
		if !ok {
			return nil, importError("parameter-refused")
		}
		// A replacement is already concrete. Re-enter only to charge its copied value.
		switch v := replacement.(type) {
		case string:
			if err := s.reserve(len(v)); err != nil {
				return nil, err
			}
		}
		return replacement, nil
	}
	var result strings.Builder
	previous := 0
	for _, match := range s.tokens.FindAllStringSubmatchIndex(value, -1) {
		if err := s.reserve(match[0] - previous); err != nil {
			return nil, err
		}
		result.WriteString(value[previous:match[0]])
		name := value[match[2]:match[3]]
		token := value[match[0]:match[1]]
		if !s.preserved[name] {
			replacement, ok := s.values[name]
			if !ok {
				return nil, importError("parameter-refused")
			}
			token = pythonScalar(replacement)
		}
		if err := s.reserve(len(token)); err != nil {
			return nil, err
		}
		result.WriteString(token)
		previous = match[1]
	}
	if err := s.reserve(len(value) - previous); err != nil {
		return nil, err
	}
	result.WriteString(value[previous:])
	return result.String(), nil
}
func (s *substitution) reserve(count int) error {
	if int64(count) > s.bytes {
		return importError("budget-exceeded")
	}
	s.bytes -= int64(count)
	return nil
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
		return v.String()
	default:
		return "None"
	}
}

func scalarEqual(left, right any) bool {
	a, aOK := left.(json.Number)
	b, bOK := right.(json.Number)
	if aOK && bOK {
		x, xOK := new(big.Rat).SetString(a.String())
		y, yOK := new(big.Rat).SetString(b.String())
		return xOK && yOK && x.Cmp(y) == 0
	}
	return left == right
}

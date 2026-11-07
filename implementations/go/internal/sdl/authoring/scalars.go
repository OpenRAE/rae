package authoring

import (
	"encoding/json"
	"math"
	"math/big"
	"strconv"
	"strings"
	"unicode"
)

func variable(value any) bool {
	s, ok := value.(string)
	if !ok || !strings.HasPrefix(s, "${") || !strings.HasSuffix(s, "}") {
		return false
	}
	parts := strings.Split(s[2:len(s)-1], ".")
	for i, part := range parts {
		if part == "__private" && i < len(parts)-1 {
			continue
		}
		if part == "" || len(part) > 64 || !portableInitial(part[0]) {
			return false
		}
		for _, r := range part {
			if !(r >= 'a' && r <= 'z' || r >= '0' && r <= '9' || r == '_' || r == '-') {
				return false
			}
		}
	}
	return true
}
func portableInitial(b byte) bool { return b >= 'a' && b <= 'z' || b >= '0' && b <= '9' }
func (w *normalizer) scalar(schema map[string]any, value any) (any, error) {
	if value == nil || variable(value) {
		return value, nil
	}
	branches := alternatives(schema)
	enums := append([]any(nil), array(schema["enum"])...)
	kinds := map[string]bool{text(schema["type"]): true}
	for _, raw := range branches {
		child, _ := w.dereference(object(raw), "")
		kinds[text(child["type"])] = true
		enums = append(enums, array(child["enum"])...)
	}
	if len(enums) > 0 {
		return normalizeEnum(value, enums)
	}
	if kinds["integer"] {
		return normalizeInteger(value, kinds["string"])
	}
	if kinds["number"] {
		return normalizeFloat(value)
	}
	if kinds["boolean"] {
		return normalizeBoolean(value, kinds["string"])
	}
	return value, nil
}
func normalizeEnum(value any, members []any) (any, error) {
	s, ok := value.(string)
	if !ok {
		return value, nil
	}
	normalized := strings.ReplaceAll(strings.ToLower(s), "-", "_")
	for _, member := range members {
		if member == value {
			return value, nil
		}
		if member == normalized {
			return normalized, nil
		}
	}
	return nil, invalid()
}
func normalizeInteger(value any, custom bool) (any, error) {
	if boolean, ok := value.(bool); ok {
		if custom {
			return nil, invalid()
		}
		if boolean {
			return json.Number("1"), nil
		}
		return json.Number("0"), nil
	}
	s := ""
	switch v := value.(type) {
	case string:
		s = strings.TrimSpace(v)
	case json.Number:
		s = v.String()
	case float64:
		if custom {
			return nil, invalid()
		}
		s = strconv.FormatFloat(v, 'g', -1, 64)
	default:
		return value, nil
	}
	integer, ok := new(big.Int).SetString(s, 10)
	if ok && (!custom || !strings.HasPrefix(s, "+")) {
		return json.Number(integer.String()), nil
	}
	if !custom {
		f, err := strconv.ParseFloat(s, 64)
		if err == nil && !math.IsInf(f, 0) && math.Trunc(f) == f {
			return json.Number(strconv.FormatFloat(f, 'f', 0, 64)), nil
		}
	}
	return nil, invalid()
}
func normalizeFloat(value any) (any, error) {
	s := ""
	switch v := value.(type) {
	case json.Number:
		s = v.String()
	case float64:
		s = strconv.FormatFloat(v, 'g', -1, 64)
	case string:
		s = strings.TrimSpace(v)
	default:
		return nil, invalid()
	}
	f, err := strconv.ParseFloat(s, 64)
	if err != nil || math.IsInf(f, 0) || math.IsNaN(f) {
		return nil, invalid()
	}
	s = strconv.FormatFloat(f, 'g', -1, 64)
	if !strings.ContainsAny(s, ".e") {
		s += ".0"
	}
	return json.Number(s), nil
}
func normalizeBoolean(value any, custom bool) (any, error) {
	if _, ok := value.(bool); ok {
		return value, nil
	}
	if number, ok := value.(json.Number); ok && !custom {
		if number == "1" {
			return true, nil
		}
		if number == "0" {
			return false, nil
		}
	}
	if s, ok := value.(string); ok {
		switch strings.ToLower(strings.TrimSpace(s)) {
		case "true", "yes", "on", "1", "y", "t":
			return true, nil
		case "false", "no", "off", "0", "n", "f":
			return false, nil
		}
	}
	return nil, invalid()
}
func ram(value any) (any, error) {
	if variable(value) {
		return value, nil
	}
	if _, ok := value.(bool); ok {
		return nil, invalid()
	}
	if n, ok := value.(json.Number); ok {
		i, ok := new(big.Int).SetString(n.String(), 10)
		if ok && i.Sign() > 0 {
			return n, nil
		}
		return nil, invalid()
	}
	s, ok := value.(string)
	if !ok {
		return nil, invalid()
	}
	s = strings.TrimSpace(s)
	if i, ok := new(big.Int).SetString(s, 10); ok && i.Sign() > 0 && !strings.HasPrefix(s, "+") && !strings.HasPrefix(s, "-") {
		return json.Number(i.String()), nil
	}
	index := strings.IndexFunc(s, func(r rune) bool { return !unicode.IsDigit(r) && r != '.' })
	if index < 1 {
		return nil, invalid()
	}
	amount, err := strconv.ParseFloat(s[:index], 64)
	if err != nil {
		return nil, invalid()
	}
	unit := strings.ToLower(strings.TrimSpace(s[index:]))
	scale := map[string]float64{"b": 1, "kb": 1000, "kib": 1024, "mb": 1e6, "mib": 1048576, "gb": 1e9, "gib": 1073741824, "tb": 1e12, "tib": 1099511627776}[unit]
	amount *= scale
	if amount < 1 || math.IsInf(amount, 0) || math.IsNaN(amount) {
		return nil, invalid()
	}
	integer, _ := new(big.Float).SetFloat64(amount).Int(nil)
	return json.Number(integer.String()), nil
}

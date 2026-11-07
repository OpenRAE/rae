package authoring

import (
	"encoding/json"
	"errors"
	"math"
	"math/big"
	"regexp"
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
		if part == privateSegment && i < len(parts)-1 {
			continue
		}
		if !localIdentifier(part) {
			return false
		}
	}
	return true
}
func localIdentifier(s string) bool {
	return len(s) > 0 && len(s) <= 64 && portableInitial(s[0]) && strings.Trim(s, "abcdefghijklmnopqrstuvwxyz0123456789_-") == ""
}
func portableInitial(b byte) bool { return b >= 'a' && b <= 'z' || b >= '0' && b <= '9' }
func normalizeEnum(value any, members []any) (any, error) {
	s, ok := value.(string)
	if !ok {
		return value, nil
	}
	normalized := strings.ReplaceAll(lower(s), "-", "_")
	for _, member := range members {
		if member == normalized {
			return normalized, nil
		}
	}
	return nil, invalid()
}
func normalizeInteger(value any, custom bool) (any, error) {
	switch v := value.(type) {
	case bool:
		if custom {
			return nil, invalid()
		}
		if v {
			return json.Number("1"), nil
		}
		return json.Number("0"), nil
	case float64:
		if custom || math.IsInf(v, 0) || math.IsNaN(v) || math.Trunc(v) != v {
			return nil, invalid()
		}
		return json.Number(strconv.FormatFloat(v, 'f', 0, 64)), nil
	case json.Number:
		return decimalInteger(v.String(), custom)
	case string:
		return decimalInteger(pythonTrim(v), custom)
	default:
		return nil, invalid()
	}
}
func decimalInteger(s string, custom bool) (any, error) {
	if s == "" {
		return nil, invalid()
	}
	negative := false
	if s[0] == '-' || s[0] == '+' {
		negative = s[0] == '-'
		if !negative && custom {
			return nil, invalid()
		}
		s = s[1:]
	}
	if !custom {
		var err error
		s, err = laxIntegerText(s)
		if err != nil {
			return nil, err
		}
	}
	digits, err := integerDigits(s, custom)
	if err != nil {
		return nil, err
	}
	integer, ok := new(big.Int).SetString(digits, 10)
	if !ok {
		return nil, invalid()
	}
	if negative {
		integer.Neg(integer)
	}
	return json.Number(integer.String()), nil
}
func integerDigits(s string, allowUnicode bool) (string, error) {
	var digits strings.Builder
	for _, r := range s {
		digit, ok := decimalDigit(r, allowUnicode)
		if !ok || digits.Len() >= 4300 {
			return "", invalid()
		}
		digits.WriteByte('0' + digit)
	}
	if digits.Len() == 0 {
		return "", invalid()
	}
	return digits.String(), nil
}
func laxIntegerText(s string) (string, error) {
	if strings.ContainsRune(s, '_') {
		for i, c := range s {
			if c == '_' && (i == 0 || i+1 == len(s) || s[i-1] < '0' || s[i-1] > '9' || s[i+1] < '0' || s[i+1] > '9') {
				return "", invalid()
			}
		}
		s = strings.ReplaceAll(s, "_", "")
	}
	if whole, fraction, present := strings.Cut(s, "."); present {
		if whole == "" || fraction == "" || strings.Trim(fraction, "0") != "" {
			return "", invalid()
		}
		s = whole
	}
	return s, nil
}
func decimalDigit(r rune, allowUnicode bool) (byte, bool) {
	if r >= '0' && r <= '9' {
		return byte(r - '0'), true
	}
	if !allowUnicode {
		return 0, false
	}
	for _, block := range unicode.Digit.R16 {
		if digit, ok := digitRange(int64(r), int64(block.Lo), int64(block.Hi), int64(block.Stride)); ok {
			return digit, true
		}
	}
	for _, block := range unicode.Digit.R32 {
		if digit, ok := digitRange(int64(r), int64(block.Lo), int64(block.Hi), int64(block.Stride)); ok {
			return digit, true
		}
	}
	return 0, false
}
func digitRange(point, low, high, stride int64) (byte, bool) {
	if point < low || point > high || (point-low)%stride != 0 {
		return 0, false
	}
	return "0123456789"[(point-low)/stride%10] - '0', true
}

func pythonTrim(s string) string {
	return strings.TrimFunc(s, func(r rune) bool { return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f })
}

var decimalFloat = regexp.MustCompile(`^[+-]?(?:[0-9](?:_?[0-9])*(?:\.(?:[0-9](?:_?[0-9])*)?)?|\.[0-9](?:_?[0-9])*)(?:[eE][+-]?[0-9](?:_?[0-9])*)?$`)

func normalizeFloat(value any) (any, error) {
	var s string
	switch v := value.(type) {
	case json.Number:
		s = v.String()
	case float64:
		s = strconv.FormatFloat(v, 'g', -1, 64)
	case string:
		s = asciiDecimalDigits(pythonTrim(v))
		if !decimalFloat.MatchString(s) {
			return nil, invalid()
		}
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
	if !custom {
		if boolean, ok := booleanNumeric(value); ok {
			return boolean, nil
		}
	}
	if s, ok := value.(string); ok {
		normalized := lower(s)
		if custom {
			normalized = lower(pythonTrim(s))
		}
		truth := map[string]bool{"true": true, "yes": true, "on": true, "1": true, "false": false, "no": false, "off": false, "0": false}
		if !custom {
			truth["y"] = true
			truth["t"] = true
			truth["n"] = false
			truth["f"] = false
		}
		if result, known := truth[normalized]; known {
			return result, nil
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
	return ramString(s)
}
func ramString(s string) (any, error) {
	s = pythonTrim(s)
	if parsed, err := decimalInteger(s, true); err == nil && !strings.HasPrefix(s, "-") && !strings.HasPrefix(s, "+") {
		if n, ok := parsed.(json.Number); ok && n != "0" {
			return n, nil
		}
		return nil, invalid()
	}
	index := strings.IndexFunc(s, func(r rune) bool { return !unicode.IsDigit(r) && r != '.' })
	if index < 1 {
		return nil, invalid()
	}
	amount, err := strconv.ParseFloat(asciiDecimalDigits(s[:index]), 64)
	if err != nil {
		return nil, invalid()
	}
	unit := lower(pythonTrim(s[index:]))
	scale := map[string]float64{"b": 1, "kb": 1000, "kib": 1024, "mb": 1e6, "mib": 1048576, "gb": 1e9, "gib": 1073741824, "tb": 1e12, "tib": 1099511627776}[unit]
	amount *= scale
	if amount < 1 || math.IsInf(amount, 0) || math.IsNaN(amount) {
		return nil, invalid()
	}
	integer, _ := new(big.Float).SetFloat64(amount).Int(nil)
	return json.Number(integer.String()), nil
}

func booleanNumeric(value any) (bool, bool) {
	switch number := value.(type) {
	case float64:
		return number == 1, number == 0 || number == 1
	case json.Number:
		parsed, err := number.Float64()
		return parsed == 1, (err == nil || errors.Is(err, strconv.ErrRange)) && (parsed == 0 || parsed == 1)
	default:
		return false, false
	}
}

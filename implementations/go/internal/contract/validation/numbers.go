package validation

import (
	"encoding/json"
	"strconv"
	"strings"
)

// boundedNumbers runs before the schema engine's exact rational conversion.
// A byte limit alone cannot bound the denominator denoted by "1e-999999999".
func boundedNumbers(value any) bool {
	switch v := value.(type) {
	case map[string]any:
		for _, child := range v {
			if !boundedNumbers(child) {
				return false
			}
		}
	case []any:
		for _, child := range v {
			if !boundedNumbers(child) {
				return false
			}
		}
	case json.Number:
		return boundedNumber(v)
	}
	return true
}

func boundedNumber(v json.Number) bool {
	coefficient, exponent, found := strings.Cut(strings.ToLower(v.String()), "e")
	digits := 0
	for _, ch := range coefficient {
		if ch >= '0' && ch <= '9' {
			digits++
		}
	}
	if digits > 4300 {
		return false
	}
	if !found {
		return true
	}
	exponent = strings.TrimLeft(strings.TrimLeft(exponent, "+-"), "0")
	if exponent == "" {
		return true
	}
	if len(exponent) > 4 {
		return false
	}
	power, err := strconv.Atoi(exponent)
	return err == nil && power <= 4300
}

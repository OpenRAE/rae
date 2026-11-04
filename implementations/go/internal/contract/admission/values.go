package admission

import (
	"encoding/json"
	"math/big"
	"slices"
	"strconv"
	"strings"
)

func object(v any) map[string]any { m, _ := v.(map[string]any); return m }
func array(v any) []any           { a, _ := v.([]any); return a }
func text(v any) string           { s, _ := v.(string); return s }
func boolean(v any) bool          { b, _ := v.(bool); return b }
func at(v any, path ...string) any {
	for _, key := range path {
		v = object(v)[key]
	}
	return v
}
func stringAt(v any, path ...string) string { return text(at(v, path...)) }
func number(v any) (*big.Rat, bool) {
	n, ok := v.(json.Number)
	if !ok {
		return nil, false
	}
	// Trusted context can also carry json.Number. Bound its representation
	// before exact conversion, as the untrusted schema boundary does.
	if !admissionNumberBound(n) {
		return nil, false
	}
	r, ok := new(big.Rat).SetString(n.String())
	return r, ok
}

func admissionNumberBound(n json.Number) bool {
	if len(n) > 8192 || !json.Valid([]byte(n)) {
		return false
	}
	coefficient, exponent, found := strings.Cut(strings.ToLower(n.String()), "e")
	digits := len(strings.ReplaceAll(strings.TrimPrefix(coefficient, "-"), ".", ""))
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
func numericEqual(a, b any) bool {
	left, ok := number(a)
	if !ok {
		return false
	}
	right, ok := number(b)
	return ok && left.Cmp(right) == 0
}
func numericGreater(a, b any) bool {
	left, lok := number(a)
	right, rok := number(b)
	return lok && rok && left.Cmp(right) > 0
}
func numericSuccessor(a, b any) bool {
	left, lok := number(a)
	right, rok := number(b)
	return lok && rok && left.Cmp(new(big.Rat).Add(right, big.NewRat(1, 1))) == 0
}
func equal(a, b any) bool {
	if left, ok := number(a); ok {
		right, ok := number(b)
		return ok && left.Cmp(right) == 0
	}
	switch left := a.(type) {
	case map[string]any:
		return equalObject(left, b)
	case []any:
		return equalArray(left, b)
	case []string:
		return equalArray(jsonStrings(left), b)
	}
	left, leftErr := json.Marshal(a)
	right, rightErr := json.Marshal(b)
	return leftErr == nil && rightErr == nil && string(left) == string(right)
}
func stringsOf(v any) []string {
	result := make([]string, 0, len(array(v)))
	for _, value := range array(v) {
		result = append(result, text(value))
	}
	return result
}
func set(v any) map[string]bool {
	result := map[string]bool{}
	for _, value := range array(v) {
		result[text(value)] = true
	}
	return result
}
func unique(values []string) bool {
	seen := map[string]bool{}
	for _, value := range values {
		if seen[value] {
			return false
		}
		seen[value] = true
	}
	return true
}
func sortedUnique(values []string) bool { return slices.IsSorted(values) && unique(values) }
func subset(values []string, allowed map[string]bool) bool {
	for _, value := range values {
		if !allowed[value] {
			return false
		}
	}
	return true
}
func fieldsUnique(v any, fields ...string) bool {
	for _, field := range fields {
		if !unique(stringsOf(at(v, field))) {
			return false
		}
	}
	return true
}
func keyed(v any, field string) bool {
	for key, value := range object(v) {
		if stringAt(value, field) != key {
			return false
		}
	}
	return true
}
func join(values ...string) string {
	encoded := []byte{'['}
	for index, value := range values {
		if index > 0 {
			encoded = append(encoded, ',')
		}
		encoded = strconv.AppendQuote(encoded, value)
	}
	return string(append(encoded, ']'))
}

func equalObject(left map[string]any, b any) bool {
	right, ok := b.(map[string]any)
	if !ok || len(left) != len(right) {
		return false
	}
	for key, value := range left {
		other, present := right[key]
		if !present || !equal(value, other) {
			return false
		}
	}
	return true
}
func equalArray(left []any, b any) bool {
	if strings, ok := b.([]string); ok {
		b = jsonStrings(strings)
	}
	right, ok := b.([]any)
	if !ok || len(left) != len(right) {
		return false
	}
	for index, value := range left {
		if !equal(value, right[index]) {
			return false
		}
	}
	return true
}

func jsonStrings(values []string) []any {
	result := make([]any, len(values))
	for index, value := range values {
		result[index] = value
	}
	return result
}

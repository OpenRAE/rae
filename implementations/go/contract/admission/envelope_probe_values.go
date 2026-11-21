package admission

import (
	"encoding/json"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
)

func uniqueProbeValues(input []any) []any {
	result := []any{}
	for _, candidate := range input {
		duplicate := false
		for _, prior := range result {
			if referenceScalarEqual(prior, candidate) {
				duplicate = true
				break
			}
		}
		if !duplicate {
			result = append(result, candidate)
		}
	}
	return result
}
func envelopePositiveValues(descriptor any) []any {
	var values []any
	switch stringAt(descriptor, termKind) {
	case postureExact:
		values = []any{at(descriptor, "value")}
	case termEnum:
		values = slices.Clone(array(at(descriptor, "values")))
	case typeBoolean:
		if at(descriptor, "value") == nil {
			values = []any{false, true}
		} else {
			values = []any{at(descriptor, "value")}
		}
	case termGovernedReference:
		for _, reference := range stringsOf(at(descriptor, "allowed_refs")) {
			values = append(values, reference)
		}
	case termNumericInterval:
		return uniqueProbeValues(positiveIntervalValues(descriptor))
	}
	slices.SortStableFunc(values, compareEnvelopeScalars)
	return uniqueProbeValues(values)
}
func positiveIntervalValues(descriptor any) []any {
	decoded, err := envelopeDomain(descriptor)
	if err != nil {
		return nil
	}
	interval, ok := decoded.(domain.Interval)
	if !ok {
		return nil
	}
	if interval.Type == domain.Integer {
		lower, _ := big.NewFloat(interval.Lower).Int(nil)
		upper, _ := big.NewFloat(interval.Upper).Int(nil)
		if !interval.LowerClosed {
			lower.Add(lower, big.NewInt(1))
		}
		if !interval.UpperClosed {
			upper.Sub(upper, big.NewInt(1))
		}
		return []any{json.Number(lower.String()), json.Number(upper.String())}
	}
	result := []any{}
	if interval.LowerClosed {
		result = append(result, interval.Lower)
	}
	result = append(result, (interval.Lower+interval.Upper)/2)
	if interval.UpperClosed {
		result = append(result, interval.Upper)
	}
	return result
}
func envelopeNegativeValues(descriptor any, enums []any) []any {
	result := []any{}
	decoded, err := envelopeDomain(descriptor)
	if err != nil {
		return result
	}
	for _, candidate := range enums {
		inside, err := domain.In(candidate, decoded)
		if err == nil && !inside {
			result = append(result, candidate)
		}
	}
	if fallback, available := outsideEnvelopeValue(descriptor); available {
		result = append(result, fallback)
	}
	return uniqueProbeValues(result)
}
func outsideEnvelopeValue(descriptor any) (any, bool) {
	switch stringAt(descriptor, termKind) {
	case postureExact:
		return perturbProbeScalar(at(descriptor, "value")), true
	case termEnum:
		return outsideFiniteValues(array(at(descriptor, "values")))
	case typeBoolean:
		if value, ok := at(descriptor, "value").(bool); ok {
			return !value, true
		}
		return nil, false
	case termGovernedReference:
		return outsideFiniteValues(array(at(descriptor, "allowed_refs")))
	case termNumericInterval:
		decoded, err := envelopeDomain(descriptor)
		if err != nil {
			return nil, false
		}
		interval, ok := decoded.(domain.Interval)
		if !ok {
			return nil, false
		}
		if interval.Type == domain.Integer {
			upper, _ := big.NewFloat(interval.Upper).Int(nil)
			if interval.UpperClosed {
				upper.Add(upper, big.NewInt(1))
			}
			return json.Number(upper.String()), true
		}
		upper := interval.Upper
		if interval.UpperClosed {
			upper++
		}
		return upper, true
	default:
		return nil, false
	}
}
func perturbProbeScalar(input any) any {
	switch value := input.(type) {
	case bool:
		return !value
	case string:
		return value + "-out-of-envelope"
	case json.Number:
		if strings.ContainsAny(value.String(), ".eE") {
			number, err := value.Float64()
			if err == nil {
				return number + 1
			}
			return nil
		}
		number, ok := new(big.Int).SetString(value.String(), 10)
		if ok {
			return json.Number(number.Add(number, big.NewInt(1)).String())
		}
	case float64:
		return value + 1
	}
	return nil
}
func outsideFiniteValues(members []any) (any, bool) {
	booleans, numeric := 0, 0
	var largest any
	var maximum *big.Rat
	for _, member := range members {
		if _, boolean := member.(bool); boolean {
			booleans++
			continue
		}
		if number, valid := referenceNumber(member); valid {
			numeric++
			if maximum == nil || number.Cmp(maximum) > 0 {
				maximum = number
				largest = member
			}
		}
	}
	if booleans == len(members) {
		return nil, false
	}
	if numeric == len(members) {
		return perturbProbeScalar(largest), true
	}
	candidate := "out-of-envelope"
	for {
		exists := slices.ContainsFunc(members, func(member any) bool { return member == candidate })
		if !exists {
			return candidate, true
		}
		candidate += "-x"
	}
}

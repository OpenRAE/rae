package authoring

import (
	"encoding/json"
	"math"
	"math/big"
	"slices"
	"strconv"
	"strings"
)

func duration(value any) (any, error) {
	if variable(value) {
		return value, nil
	}
	switch v := value.(type) {
	case json.Number:
		n, ok := new(big.Int).SetString(v.String(), 10)
		if !ok || n.Sign() < 0 {
			return nil, invalid()
		}
		return v, nil
	case float64:
		if v < 0 || math.IsInf(v, 0) || math.IsNaN(v) {
			return nil, invalid()
		}
		return json.Number(strconv.FormatFloat(math.Ceil(v), 'f', 0, 64)), nil
	case string:
		return durationString(v)
	default:
		return nil, invalid()
	}
}
func durationString(value string) (any, error) {
	normalized := strings.NewReplacer("_", "", " ", "", "µ", "u").Replace(strings.ToLower(strings.TrimSpace(value)))
	if normalized == "" {
		return nil, invalid()
	}
	units := durationUnits()
	names := make([]string, 0, len(units))
	for name := range units {
		names = append(names, name)
	}
	slices.SortFunc(names, func(a, b string) int { return len(b) - len(a) })
	total := new(big.Rat)
	found := false
	for position := 0; position < len(normalized); {
		if normalized[position] == '+' {
			position++
			continue
		}
		end := durationNumberEnd(normalized, position)
		if end == position {
			return nil, invalid()
		}
		amount, ok := new(big.Rat).SetString(normalized[position:end])
		if !ok {
			return nil, invalid()
		}
		found = true
		position = end
		scale, consumed := durationScale(normalized[position:], names, units)
		amount.Mul(amount, scale)
		position += consumed
		total.Add(total, amount)
	}
	if !found {
		return nil, invalid()
	}
	result, remainder := new(big.Int), new(big.Int)
	result.QuoRem(total.Num(), total.Denom(), remainder)
	if remainder.Sign() != 0 {
		result.Add(result, big.NewInt(1))
	}
	return json.Number(result.String()), nil
}
func durationScale(value string, names []string, units map[string]string) (*big.Rat, int) {
	for _, name := range names {
		if strings.HasPrefix(value, name) {
			scale, _ := new(big.Rat).SetString(units[name])
			return scale, len(name)
		}
	}
	return big.NewRat(1, 1), 0
}
func durationNumberEnd(s string, start int) int {
	i := start
	for i < len(s) && s[i] >= '0' && s[i] <= '9' {
		i++
	}
	if i == start {
		return start
	}
	if i+1 < len(s) && s[i] == '.' && s[i+1] >= '0' && s[i+1] <= '9' {
		i++
		for i < len(s) && s[i] >= '0' && s[i] <= '9' {
			i++
		}
	}
	return i
}
func durationUnits() map[string]string {
	groups := map[string][]string{
		"31536000": {"y", "year", "years"}, "2592000": {"mon", "month", "months"}, "604800": {"w", "week", "weeks"}, "86400": {"d", "day", "days"}, "3600": {"h", "hr", "hour", "hours"}, "60": {"m", "min", "mins", "minute", "minutes"}, "1": {"s", "sec", "secs", "second", "seconds"}, "0.001": {"ms", "msec", "millisecond", "milliseconds"}, "0.000001": {"us", "usec", "usecond", "microsecond", "microseconds"}, "0.000000001": {"ns", "nsec", "nanosecond", "nanoseconds"},
	}
	result := map[string]string{}
	for scale, names := range groups {
		for _, name := range names {
			result[name] = scale
		}
	}
	return result
}

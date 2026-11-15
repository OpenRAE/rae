package admission

import (
	"encoding/json"
	"errors"
	"math"
	"math/big"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"go.yaml.in/yaml/v3"
)

type experimentUnsupported struct{ key string }
type experimentScalarRules struct{ integer, floating, timestamp *regexp.Regexp }

var experimentScalarPatterns = sync.OnceValue(func() experimentScalarRules { //nolint:gochecknoglobals // Immutable scalar policy, with no source values.
	return experimentScalarRules{
		integer:   regexp.MustCompile(`^[-+]?(?:0b[0-1_]+|0[0-7_]+|(?:0|[1-9][0-9_]*)|0x[0-9a-fA-F_]+|[1-9][0-9_]*(?::[0-5]?[0-9])+)$`),
		floating:  regexp.MustCompile(`^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|[-+]?\.[0-9_]+(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$`),
		timestamp: regexp.MustCompile(`^[0-9]{4}-[0-9]{2}-[0-9]{2}$|^[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}[Tt \t]+[0-9]{1,2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?$`),
	}
})

func experimentScalar(node *yaml.Node) (any, error) {
	tag := node.Tag
	if node.Style&yaml.TaggedStyle == 0 {
		if node.Style != 0 {
			return node.Value, nil
		}
		tag = experimentImplicitTag(node.Value)
	}
	switch tag {
	case "!!str":
		return node.Value, nil
	case "!!null":
		return nil, nil //nolint:nilnil // YAML null is a valid scalar value.
	case "!!bool":
		switch strings.ToLower(node.Value) {
		case "yes", "true", "on":
			return true, nil
		case "no", "false", "off":
			return false, nil
		default:
			return nil, experimentError("invalid-yaml")
		}
	case "!!int":
		return experimentInteger(node.Value)
	case "!!float":
		return experimentFloat(node.Value)
	case "!!timestamp":
		if !experimentTimestamp(node.Value) {
			return nil, experimentError("invalid-yaml")
		}
		return experimentUnsupported{key: node.Value}, nil
	case "!!binary":
		decoded, err := experimentBinaryDecode(node.Value)
		if err != nil {
			return nil, err
		}
		return experimentBinary{data: decoded}, nil
	default:
		return nil, experimentError("invalid-yaml")
	}
}

func experimentImplicitTag(text string) string {
	switch text {
	case "<<":
		return "!!merge"
	case "", "~", termNull, "Null", "NULL":
		return "!!null"
	case "yes", "Yes", "YES", "no", "No", "NO", "true", "True", "TRUE", "false", "False", "FALSE", "on", "On", "ON", "off", "Off", "OFF":
		return "!!bool"
	}
	rules := experimentScalarPatterns()
	if rules.integer.MatchString(text) {
		return "!!int"
	}
	if rules.floating.MatchString(text) {
		return "!!float"
	}
	if rules.timestamp.MatchString(text) {
		return "!!timestamp"
	}
	return "!!str"
}

func experimentInteger(text string) (any, error) {
	clean := strings.ReplaceAll(text, "_", "")
	sign := 1
	if strings.HasPrefix(clean, "-") {
		sign = -1
		clean = clean[1:]
	} else {
		clean = strings.TrimPrefix(clean, "+")
	}
	result := new(big.Int)
	if strings.Contains(clean, ":") {
		if err := experimentSexagesimal(result, clean); err != nil {
			return nil, err
		}
	} else {
		if err := experimentBasedInteger(result, clean); err != nil {
			return nil, err
		}
	}
	if sign < 0 {
		result.Neg(result)
	}
	return json.Number(result.String()), nil
}

func experimentSexagesimal(result *big.Int, clean string) error {
	for part := range strings.SplitSeq(clean, ":") {
		n, ok := new(big.Int).SetString(part, 10)
		if !ok {
			return experimentError("invalid-yaml")
		}
		result.Mul(result, big.NewInt(60))
		result.Add(result, n)
	}
	return nil
}
func experimentBasedInteger(result *big.Int, clean string) error {
	base := 10
	switch {
	case strings.HasPrefix(clean, "0b"):
		base = 2
		clean = clean[2:]
	case strings.HasPrefix(clean, "0x"):
		base = 16
		clean = clean[2:]
	case len(clean) > 1 && clean[0] == '0':
		base = 8
		clean = clean[1:]
	}
	if base == 10 && len(clean) > 4300 {
		return experimentError("invalid-yaml")
	}
	if _, ok := result.SetString(clean, base); !ok {
		return experimentError("invalid-yaml")
	}
	return nil
}
func experimentFloat(text string) (any, error) {
	clean := strings.ReplaceAll(text, "_", "")
	lower := strings.ToLower(clean)
	if strings.TrimLeft(lower, "+-") == ".inf" {
		if strings.HasPrefix(lower, "-") {
			return math.Inf(-1), nil
		}
		return math.Inf(1), nil
	}
	if lower == ".nan" {
		return math.NaN(), nil
	}
	sign := 1.0
	if strings.HasPrefix(clean, "-") {
		sign = -1
		clean = clean[1:]
	} else {
		clean = strings.TrimPrefix(clean, "+")
	}
	var result float64
	for part := range strings.SplitSeq(clean, ":") {
		n, err := strconv.ParseFloat(part, 64)
		if err != nil && !errors.Is(err, strconv.ErrRange) {
			return nil, experimentError("invalid-yaml")
		}
		result = result*60 + n
	}
	result *= sign
	if math.IsNaN(result) || math.IsInf(result, 0) {
		return result, nil
	}
	rendered := strconv.FormatFloat(result, 'g', -1, 64)
	if !strings.ContainsAny(rendered, ".eE") {
		rendered += ".0"
	}
	return json.Number(rendered), nil
}

func experimentTimestamp(text string) bool {
	if !experimentScalarPatterns().timestamp.MatchString(text) {
		return false
	}
	date := strings.FieldsFunc(text, func(r rune) bool { return r == 'T' || r == 't' || r == ' ' || r == '\t' })[0]
	parts := strings.Split(date, "-")
	if len(parts) != 3 {
		return false
	}
	y, err := strconv.Atoi(parts[0])
	if err != nil || y < 1 {
		return false
	}
	m, err := strconv.Atoi(parts[1])
	if err != nil {
		return false
	}
	d, err := strconv.Atoi(parts[2])
	if err != nil {
		return false
	}
	day := time.Date(y, time.Month(m), d, 0, 0, 0, 0, time.UTC)
	if day.Year() != y || int(day.Month()) != m || day.Day() != d {
		return false
	}
	if len(text) == 10 {
		return true
	}
	return experimentTimestampClock(text[len(date):])
}

func experimentTimestampClock(text string) bool {
	clock := strings.TrimLeft(text, "Tt \t")
	zoneStart := strings.IndexAny(clock, "Z+-")
	zone := ""
	if zoneStart >= 0 {
		zone = strings.TrimSpace(clock[zoneStart:])
		clock = clock[:zoneStart]
	}
	parts := strings.Split(strings.TrimSpace(clock), ":")
	if len(parts) != 3 {
		return false
	}
	for index, part := range parts {
		if index == 2 {
			part, _, _ = strings.Cut(part, ".")
		}
		n, err := strconv.Atoi(part)
		if err != nil || n >= []int{24, 60, 60}[index] {
			return false
		}
	}
	if zone == "" || zone == "Z" {
		return true
	}
	parts = strings.Split(zone[1:], ":")
	hours, err := strconv.Atoi(parts[0])
	if err != nil {
		return false
	}
	minutes := 0
	if len(parts) > 1 {
		minutes, err = strconv.Atoi(parts[1])
	}
	// datetime.timezone bounds the total offset, rather than each component.
	return err == nil && hours*60+minutes < 24*60
}

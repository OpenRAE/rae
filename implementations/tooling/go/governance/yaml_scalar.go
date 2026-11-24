package governance

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"math"
	"math/big"
	"regexp"
	"strconv"
	"strings"
	"time"

	"go.yaml.in/yaml/v3"
)

type yamlDate struct{ time.Time }
type yamlTimestamp struct {
	time.Time

	aware bool
}
type yamlBinary string

func yamlScalar(node *yaml.Node) (any, error) {
	tag := node.Tag
	if node.Style == 0 {
		tag = pythonYAMLTag(node.Value)
	}
	switch tag {
	case "!!str", "!!value":
		return node.Value, nil
	case "!!null":
		return nil, nil //nolint:nilnil // A YAML null is a successfully constructed value.
	case "!!binary":
		return yamlBinaryValue(node.Value)
	case "!!bool":
		return yamlBoolean(node.Value)
	case "!!int":
		return yamlInteger(node.Value)
	case "!!float":
		return yamlFloat(node.Value)
	case "!!timestamp":
		return yamlTime(node.Value)
	default:
		return nil, errors.New("unsupported YAML constructor")
	}
}

func yamlBinaryValue(value string) (yamlBinary, error) {
	for _, r := range value {
		if r > 127 {
			return "", errors.New("YAML binary source is not ASCII")
		}
	}
	filtered := strings.Map(func(r rune) rune {
		if r < 128 && strings.ContainsRune("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=", r) {
			return r
		}
		return -1
	}, value)
	normalized, err := yamlBinaryPadding(filtered)
	if err != nil {
		return "", err
	}
	data, err := base64.StdEncoding.DecodeString(normalized)
	return yamlBinary(data), err
}

// Python's binary constructor tolerates surplus padding, including padding
// between complete groups, but refuses data after a padded final group.
func yamlBinaryPadding(value string) (string, error) {
	var out strings.Builder
	padding, finished := 0, false
	for _, char := range value {
		if char != '=' {
			if finished {
				return "", errors.New("YAML binary data follows final padding")
			}
			out.WriteRune(char)
			padding = 0
			continue
		}
		count := out.Len() % 4
		if count < 2 || finished {
			continue
		}
		padding++
		needed := 4 - count
		if padding == needed {
			out.WriteString(strings.Repeat("=", needed))
			finished = true
		}
	}
	return out.String(), nil
}

func yamlBoolean(value string) (bool, error) {
	switch strings.ToLower(value) {
	case "yes", trueLiteral, "on":
		return true, nil
	case "no", "false", "off":
		return false, nil
	default:
		return false, errors.New("invalid YAML boolean")
	}
}

func pythonYAMLTag(value string) string {
	resolvers := []struct{ tag, pattern string }{
		{"!!bool", `^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$`},
		{"!!null", `^(?:~|null|Null|NULL|)$`},
		{"!!float", `^(?:[-+]?[0-9][0-9_]*\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$`},
		{"!!int", `^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$`},
		{"!!timestamp", `^(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt]|[ \t]+)[0-9]{1,2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?)$`},
	}
	for _, resolver := range resolvers {
		if regexp.MustCompile(resolver.pattern).MatchString(value) {
			return resolver.tag
		}
	}
	return "!!str"
}

func yamlInteger(value string) (any, error) {
	value = strings.ReplaceAll(value, "_", "")
	value, sign := yamlSign(value)
	base := 10
	switch {
	case strings.HasPrefix(value, "0x"):
		base, value = 16, value[2:]
	case strings.HasPrefix(value, "0b"):
		base, value = 2, value[2:]
	case strings.HasPrefix(value, "0o"):
		base, value = 8, value[2:]
	case strings.HasPrefix(value, "0") && len(value) > 1:
		base = 8
	}
	if base == 10 && strings.Contains(value, ":") {
		return yamlSexagesimalInteger(value, sign)
	}
	if base == 10 && len(value) > 4300 {
		return nil, errors.New("YAML integer exceeds digit limit")
	}
	integer, ok := new(big.Int).SetString(value, base)
	if !ok {
		return nil, errors.New("invalid YAML integer")
	}
	if sign < 0 {
		integer.Neg(integer)
	}
	return json.Number(integer.String()), nil
}

func yamlSexagesimalInteger(value string, sign int) (any, error) {
	integer := new(big.Int)
	for part := range strings.SplitSeq(value, ":") {
		if len(strings.TrimLeft(part, "+-")) > 4300 {
			return nil, errors.New("YAML integer exceeds digit limit")
		}
		segment, ok := new(big.Int).SetString(part, 10)
		if !ok {
			return nil, errors.New("invalid YAML integer")
		}
		integer.Mul(integer, big.NewInt(60))
		integer.Add(integer, segment)
	}
	if sign < 0 {
		integer.Neg(integer)
	}
	return json.Number(integer.String()), nil
}

func yamlFloat(value string) (float64, error) {
	value = strings.ToLower(strings.ReplaceAll(value, "_", ""))
	value, integerSign := yamlSign(value)
	sign := float64(integerSign)
	switch value {
	case ".inf":
		return math.Inf(integerSign), nil
	case ".nan":
		return math.NaN(), nil
	}
	if !strings.Contains(value, ":") {
		result, err := strconv.ParseFloat(value, 64)
		if errors.Is(err, strconv.ErrRange) {
			return sign * result, nil
		}
		return sign * result, err
	}
	total := 0.0
	for part := range strings.SplitSeq(value, ":") {
		number, err := strconv.ParseFloat(part, 64)
		if err != nil {
			return 0, err
		}
		total = total*60 + number
	}
	return sign * total, nil
}

func yamlSign(value string) (string, int) {
	sign := 1
	if strings.HasPrefix(value, "-") {
		sign = -1
	}
	if strings.HasPrefix(value, "-") || strings.HasPrefix(value, "+") {
		value = value[1:]
	}
	return value, sign
}

func yamlTime(value string) (any, error) {
	parts := regexp.MustCompile(`^([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?:(?:[Tt]|[ \t]+)([0-9]{1,2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]*))?(?:[ \t]*(Z|([-+])([0-9]{1,2})(?::([0-9]{2}))?))?)?$`).FindStringSubmatch(value)
	if parts == nil {
		return nil, errors.New("invalid YAML timestamp")
	}
	fields := make([]int, len(parts))
	for i, part := range parts {
		if regexp.MustCompile(`^[0-9]+$`).MatchString(part) {
			fields[i], _ = strconv.Atoi(part)
		}
	}
	fraction := parts[7] + "000000"
	microsecond, err := strconv.Atoi(fraction[:6])
	if err != nil {
		return nil, err
	}
	offset := fields[10]*3600 + fields[11]*60
	if parts[9] == "-" {
		offset = -offset
	}
	if offset <= -86400 || offset >= 86400 {
		return nil, errors.New("invalid YAML timezone")
	}
	zone := time.FixedZone("", offset)
	date := time.Date(fields[1], time.Month(fields[2]), fields[3], fields[4], fields[5], fields[6], microsecond*1000, zone)
	if fields[1] < 1 || date.Year() != fields[1] || int(date.Month()) != fields[2] || date.Day() != fields[3] || date.Hour() != fields[4] || date.Minute() != fields[5] || date.Second() != fields[6] {
		return nil, errors.New("invalid YAML date or time")
	}
	if parts[4] == "" {
		return yamlDate{date}, nil
	}
	return yamlTimestamp{Time: date, aware: parts[8] != ""}, nil
}

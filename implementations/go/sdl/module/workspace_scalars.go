package module

import (
	"errors"
	"regexp"
	"strconv"
	"strings"
)

// These are the unchanged SafeLoader resolver forms, rather than SDL Core.
var (
	workspaceBool  = regexp.MustCompile(`^(?:yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$`)
	workspaceInt   = regexp.MustCompile(`^[-+]?(?:0b[0-1_]+|0[0-7_]+|(?:0|[1-9][0-9_]*)|0x[0-9a-fA-F_]+|[1-9][0-9_]*(?::[0-5]?[0-9])+)$`)
	workspaceFloat = regexp.MustCompile(`^(?:[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$`)
)

// Trust fields accept only strings, flags and mappings. Other constructed
// scalar types stay distinct from strings and cannot satisfy those fields.
type workspaceOtherScalar struct{}

func workspaceScalar(raw string) (any, error) {
	switch raw {
	case "~", nullType, "Null", "NULL", "":
		return nil, nil //nolint:nilnil // YAML null is a valid constructed value before trust-field checks.
	case "=":
		return nil, invalid()
	}
	if workspaceBool.MatchString(raw) {
		return lower(raw) == "yes" || lower(raw) == "true" || lower(raw) == "on", nil
	}
	if matched, err := workspaceTimestamp(raw); matched {
		return workspaceOtherScalar{}, err
	}
	if workspaceFloat.MatchString(raw) {
		return workspaceFloatValue(raw)
	}
	if workspaceInt.MatchString(raw) {
		return workspaceIntValue(raw)
	}
	return raw, nil
}
func workspaceIntValue(raw string) (any, error) {
	clean := strings.ReplaceAll(raw, "_", "")
	negative := strings.HasPrefix(clean, "-")
	clean = strings.TrimLeft(clean, "+-")
	if strings.Contains(clean, ":") {
		return workspaceOtherScalar{}, nil
	}
	base := 10
	switch {
	case strings.HasPrefix(clean, "0x"):
		base = 16
		clean = clean[2:]
	case strings.HasPrefix(clean, "0b"):
		base = 2
		clean = clean[2:]
	case len(clean) > 1 && clean[0] == '0':
		base = 8
	}
	if clean == "" || base == 10 && len(clean) > 4300 {
		return nil, invalid()
	}
	digits := strings.TrimLeft(clean, "0")
	if digits == "" {
		return false, nil
	}
	if digits == "1" && !negative {
		return true, nil
	}
	return workspaceOtherScalar{}, nil
}
func workspaceFloatValue(raw string) (any, error) {
	clean := strings.ReplaceAll(raw, "_", "")
	sign := 1.0
	if strings.HasPrefix(clean, "-") {
		sign = -1
	}
	if strings.Contains(clean, ":") {
		clean = strings.TrimLeft(clean, "+-")
		value := 0.0
		for part := range strings.SplitSeq(clean, ":") {
			n, err := strconv.ParseFloat(part, 64)
			if err != nil && !errors.Is(err, strconv.ErrRange) {
				return nil, invalid()
			}
			value = value*60 + n
		}
		return workspaceNumericFlag(value * sign), nil
	}
	normalized := strings.ToLower(clean)
	if strings.Contains(normalized, "inf") || strings.Contains(normalized, "nan") {
		return workspaceOtherScalar{}, nil
	}
	number, err := strconv.ParseFloat(clean, 64)
	if err != nil && !errors.Is(err, strconv.ErrRange) {
		return nil, invalid()
	}
	return workspaceNumericFlag(number), nil
}
func workspaceNumericFlag(value float64) any {
	if value == 0 {
		return false
	}
	if value == 1 {
		return true
	}
	return workspaceOtherScalar{}
}

package authoring

import (
	"strings"
	"unicode"
)

type versionRequirement struct {
	specifiers   []versionSpecifier
	unrestricted bool
	requested    string
}
type versionSpecifier struct {
	operator, raw string
	version       pepVersion
	wildcard      bool
	digits        bool
}

func versionSpec(requested string) (versionRequirement, error) {
	result := versionRequirement{requested: requested}
	value := pythonTrim(requested)
	if value == "" || value == "*" {
		result.unrestricted = true
		return result, nil
	}
	if !strings.ContainsAny(value, "<>!=~") {
		value = "==" + value
	}
	for _, part := range strings.Split(value, ",") {
		part = pythonTrim(part)
		if part == "" {
			continue
		}
		spec, err := parseSpecifier(part)
		if err != nil {
			return result, err
		}
		result.specifiers = append(result.specifiers, spec)
	}
	return result, nil
}
func splitSpecifier(s string) (string, string) {
	for _, operator := range []string{"===", "==", "!=", "<=", ">=", "~=", "<", ">"} {
		if rest, ok := strings.CutPrefix(s, operator); ok {
			return operator, pythonTrim(rest)
		}
	}
	return "", s
}
func parseSpecifier(part string) (versionSpecifier, error) {
	operator, raw := splitSpecifier(part)
	spec := versionSpecifier{operator: operator, raw: raw}
	if operator == "" {
		return spec, invalid()
	}
	if operator == "===" {
		if strings.ContainsAny(raw, ";)") || strings.ContainsFunc(raw, unicode.IsSpace) {
			return spec, invalid()
		}
		return spec, nil
	}
	if raw == "" {
		return spec, invalid()
	}
	versionText := raw
	if strings.HasSuffix(raw, ".*") {
		if operator != "==" && operator != "!=" {
			return spec, invalid()
		}
		spec.wildcard = true
		versionText = strings.TrimSuffix(raw, ".*")
	}
	version, status := parsePEP(versionText)
	if status == versionInvalid {
		return spec, invalid()
	}
	if spec.wildcard && !version.plainRelease() {
		return spec, invalid()
	}
	if operator != "==" && operator != "!=" && len(version.local) > 0 {
		return spec, invalid()
	}
	if operator == "~=" && len(version.release) < 2 {
		return spec, invalid()
	}
	spec.version = version
	spec.digits = status == versionDigits
	return spec, nil
}
func (r versionRequirement) accepts(actual string) bool {
	if r.unrestricted {
		return true
	}
	candidate, status := parsePEP(actual)
	if status == versionInvalid {
		return actual == r.requested
	}
	if status == versionDigits {
		return false
	}
	for _, specifier := range r.specifiers {
		if !specifier.accepts(candidate) {
			return false
		}
	}
	return true
}
func (s versionSpecifier) accepts(candidate pepVersion) bool {
	if s.digits {
		return false
	}
	switch s.operator {
	case "===":
		return strings.EqualFold(candidate.canonical(), s.raw)
	case "==":
		return s.equal(candidate)
	case "!=":
		return !s.equal(candidate)
	case ">=":
		return candidate.compare(s.version, false) >= 0
	case "<=":
		return candidate.compare(s.version, false) <= 0
	case "~=":
		return candidate.compare(s.version, false) >= 0 && candidate.prefix(s.version, len(s.version.release)-1)
	case "<":
		return candidate.compare(s.version, true) < 0 && (s.version.prerelease() || !candidate.prerelease() || candidate.baseCompare(s.version) != 0)
	case ">":
		return s.greater(candidate)
	default:
		return false
	}
}
func (s versionSpecifier) equal(candidate pepVersion) bool {
	if s.wildcard {
		return candidate.prefix(s.version, len(s.version.release))
	}
	return candidate.compare(s.version, len(s.version.local) > 0) == 0
}
func (s versionSpecifier) greater(candidate pepVersion) bool {
	if candidate.compare(s.version, true) <= 0 {
		return false
	}
	sameBase := candidate.baseCompare(s.version) == 0
	if !s.version.hasPost && candidate.hasPost && sameBase {
		return false
	}
	return len(candidate.local) == 0 || !sameBase
}

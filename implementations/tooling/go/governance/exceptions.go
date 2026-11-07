package governance

import (
	"errors"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const exceptionPath = "tools/policy/exceptions.yaml"
const invalidExceptions = "tools/policy/exceptions.yaml is not a valid policy exceptions document"

type policyInputError string

func (e policyInputError) Error() string { return string(e) }

func loadExceptions(r *repository) (any, error) {
	data, err := r.read(exceptionPath)
	if err != nil {
		return nil, err
	}
	value, err := yamlValue(data, true)
	if err != nil {
		return nil, exceptionLoadError(err)
	}
	m, ok := value.(*mapping)
	if !ok {
		return nil, policyInputError(invalidExceptions)
	}
	return m.get("exceptions"), nil
}

func exceptionLoadError(err error) error {
	if _, syntax := errors.AsType[*yamlSyntaxError](err); syntax {
		return policyInputError(invalidExceptions)
	}
	if strings.Contains(err.Error(), "constructor depth") {
		return policyInputError("exceptions.yaml nests beyond the YAML parser depth")
	}
	return policyInputError("exceptions.yaml contains a YAML value that cannot be constructed")
}

func applyExceptions(findings []Finding, value any, uid, today string) ([]Finding, error) {
	if len(findings) == 0 || !truth(value) {
		return findings, nil
	}
	entries, ok := value.([]any)
	if !ok {
		switch value.(type) {
		case string, *mapping, yamlSet, yamlBinary:
			return nil, policyInputError(invalidExceptions)
		default:
			return nil, errors.New("policy exception collection is not iterable")
		}
	}
	remaining := []Finding{}
	for _, f := range findings {
		waived, err := waivedFinding(f, entries, uid, today)
		if err != nil {
			return nil, err
		}
		if !waived {
			remaining = append(remaining, f)
		}
	}
	return remaining, nil
}

func waivedFinding(f Finding, entries []any, uid, today string) (bool, error) {
	for _, value := range entries {
		entry, ok := value.(*mapping)
		if !ok {
			return false, policyInputError(invalidExceptions)
		}
		active, err := exceptionActive(entry, today)
		if err != nil {
			return false, err
		}
		if !active || entry.get("rule_id") != f.RuleID {
			continue
		}
		matches, err := exceptionSelectors(f.Path, entry, uid)
		if err != nil {
			return false, err
		}
		if matches {
			return true, nil
		}
	}
	return false, nil
}

func exceptionSelectors(file *string, entry *mapping, uid string) (bool, error) {
	matches, err := exceptionRequirement(entry.get("requirement_uid"), uid)
	if err != nil || !matches {
		return false, err
	}
	return exceptionPaths(file, entry.get("paths"))
}

func exceptionActive(entry *mapping, today string) (bool, error) {
	expires := entry.get("expires_at")
	if !truth(expires) {
		return true, nil
	}
	expiry, valid := pythonISODate(pythonStr(expires))
	if !valid {
		return false, policyInputError("policy exception expires_at must be an ISO date")
	}
	current, err := time.Parse(time.DateOnly, today)
	if err != nil {
		return false, err
	}
	return !current.After(expiry), nil
}

func exceptionRequirement(value any, uid string) (bool, error) {
	if uid == "" {
		return true, nil
	}
	if !yamlHashable(value) {
		return false, policyInputError(invalidExceptions)
	}
	return value == nil || value == uid, nil
}

func exceptionPaths(file *string, value any) (bool, error) {
	if file == nil || *file == "" || !truth(value) {
		return true, nil
	}
	paths, valid := exceptionTextItems(value)
	if !valid {
		return false, policyInputError(invalidExceptions)
	}
	for _, prefix := range paths {
		if pathPrefix(*file, prefix) {
			return true, nil
		}
	}
	return false, nil
}

func exceptionTextItems(value any) ([]string, bool) {
	switch v := value.(type) {
	case string:
		items := make([]string, 0, len(v))
		for _, r := range v {
			items = append(items, string(r))
		}
		return items, true
	case *mapping:
		return stringList(v.keys, false)
	case yamlSet:
		return stringList(v.items.keys, false)
	default:
		return stringList(value, false)
	}
}

func pathPrefix(value, prefix string) bool {
	value, prefix = prefixPath(value), prefixPath(prefix)
	return value == prefix || strings.HasPrefix(value, prefix+"/")
}

func pythonISODate(value string) (time.Time, bool) {
	for _, layout := range []string{time.DateOnly, "20060102"} {
		if date, err := time.Parse(layout, value); err == nil && date.Year() > 0 {
			return date, true
		}
	}
	match := regexp.MustCompile(`^([0-9]{4})(?:-W([0-9]{2})(?:-([0-9]))?|W([0-9]{2})([0-9])?)$`).FindStringSubmatch(value)
	if match == nil {
		return time.Time{}, false
	}
	year, _ := strconv.Atoi(match[1])
	weekText, dayText := match[2], match[3]
	if weekText == "" {
		weekText, dayText = match[4], match[5]
	}
	week, _ := strconv.Atoi(weekText)
	day := 1
	if dayText != "" {
		day, _ = strconv.Atoi(dayText)
	}
	if year < 1 || week < 1 || week > 53 || day < 1 || day > 7 {
		return time.Time{}, false
	}
	jan4 := time.Date(year, time.January, 4, 0, 0, 0, 0, time.UTC)
	weekday := (int(jan4.Weekday()) + 6) % 7
	date := jan4.AddDate(0, 0, (week-1)*7+day-1-weekday)
	isoYear, isoWeek := date.ISOWeek()
	return date, isoYear == year && isoWeek == week && date.Year() <= 9999
}

func (c *checker) finish(r *repository, findings []Finding) (Report, error) {
	if !r.file(exceptionPath) {
		return finish(findings), nil
	}
	entries, err := loadExceptions(r)
	if err != nil {
		return Report{}, err
	}
	findings, err = applyExceptions(findings, entries, "", c.request.Today)
	return finish(findings), err
}

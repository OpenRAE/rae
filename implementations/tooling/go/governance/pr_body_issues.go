package governance

import (
	"context"
	"errors"
	"regexp"
	"strings"

	"golang.org/x/text/cases"
)

type prIssueFacts struct {
	exists, open bool
	uids         []string
}

type prIssueLookup func(context.Context, string) (prIssueFacts, error)
type prLookupError string

func (e prLookupError) Error() string { return string(e) }

type prIssueReference struct{ keyword, number string }

func prIssueNumbers(body, keyword string) []string {
	result := []string{}
	seen := map[string]bool{}
	for _, line := range pythonLines(prStripIgnored(body), false) {
		parts := strings.FieldsFunc(strings.Trim(line, " \t"), pythonWhitespace)
		if len(parts) != 2 || parts[0] != keyword || !strings.HasPrefix(parts[1], "#") {
			continue
		}
		number := parts[1][1:]
		if len(number) == 0 || len(number) > 4300 || number[0] == '0' || strings.IndexFunc(number, func(r rune) bool { return r < '0' || r > '9' }) >= 0 {
			continue
		}
		if !seen[number] {
			seen[number] = true
			result = append(result, number)
		}
	}
	return result
}

func prNoIssueReasons(body string) []string {
	result := []string{}
	for _, line := range pythonLines(prStripIgnored(body), false) {
		if reason, found := strings.CutPrefix(strings.Trim(line, " \t"), "No issue:"); found {
			result = append(result, strings.TrimFunc(reason, pythonWhitespace))
		}
	}
	return result
}

func prRequirementUIDs(body string) []string {
	uid := regexp.MustCompile(`^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[A-Z0-9]*[0-9]$`)
	separator := regexp.MustCompile(`(?:` + pythonSpace() + `|[,;])+`)
	result := []string{}
	seen := map[string]bool{}
	for _, line := range prRequirementLines(body) {
		for _, candidate := range prLeadingUIDs(line, uid, separator) {
			if !seen[candidate] {
				seen[candidate] = true
				result = append(result, candidate)
			}
		}
	}
	return result
}

func prRequirementLines(body string) []string {
	heading := regexp.MustCompile(`^(#{1,6})` + pythonSpace() + `(.+)$`)
	level := 0
	result := []string{}
	for _, line := range pythonLines(body, false) {
		if match := heading.FindStringSubmatch(line); match != nil {
			depth := len(match[1])
			if level > 0 && depth <= level {
				break
			}
			if level == 0 && depth >= 2 && depth <= 4 && cases.Fold().String(strings.TrimFunc(match[2], pythonWhitespace)) == "requirements" {
				level = depth
			}
			continue
		}
		if level > 0 {
			result = append(result, line)
		}
	}
	return result
}

func prLeadingUIDs(line string, uid, separator *regexp.Regexp) []string {
	line = strings.TrimLeftFunc(line, pythonWhitespace)
	if len(line) < 2 || !strings.ContainsRune("-*+", rune(line[0])) {
		return nil
	}
	rest := strings.TrimLeftFunc(line[1:], pythonWhitespace)
	if rest == line[1:] || rest == "" {
		return nil
	}
	result := []string{}
	for _, token := range separator.Split(rest, -1) {
		candidate := strings.TrimRight(strings.TrimLeft(token, "`[("), "`)].:")
		if len(candidate) > 50 || !uid.MatchString(candidate) {
			break
		}
		result = append(result, candidate)
	}
	return result
}

func prInspectIssue(ctx context.Context, reference prIssueReference, lookup prIssueLookup) (*Finding, error) {
	issue, err := lookup(ctx, reference.number)
	message := ""
	switch {
	case err != nil:
		if _, expected := errors.AsType[prLookupError](err); !expected {
			return nil, err
		}
		message = "Could not verify issue #" + reference.number + ": " + err.Error()
	case !issue.exists:
		message = reference.keyword + " #" + reference.number + " does not target an issue in this repository."
	case !issue.open:
		message = reference.keyword + " #" + reference.number + " targets an issue that is not open."
	default:
		expected := "Closes"
		if len(issue.uids) > 0 {
			expected = "Refs"
		}
		if reference.keyword != expected {
			message = "Issue #" + reference.number + " requires '" + expected + " #" + reference.number + "' for its requirement scope."
		}
	}
	if message == "" {
		return nil, nil //nolint:nilnil // A verified issue produces no violation.
	}
	failure := finding("issue-tracking", message, "")
	return &failure, nil
}

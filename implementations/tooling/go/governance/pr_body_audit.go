package governance

import (
	"context"
	"errors"
	"strings"
)

func prOpenIssueReport(ctx context.Context, body string, lookup prIssueLookup, number string) (string, error) {
	closing := prIssueNumbers(body, "Closes")
	references := prIssueNumbers(body, "Refs")
	reasons := prNoIssueReasons(body)
	open := []string{}
	inspection := []string{}
	for _, candidate := range closing {
		issue, err := lookup(ctx, candidate)
		switch {
		case err != nil:
			if _, expected := errors.AsType[prLookupError](err); !expected {
				return "", err
			}
			inspection = append(inspection, "- Could not inspect `#"+candidate+"`: "+err.Error())
		case !issue.exists:
			inspection = append(inspection, "- Could not inspect `#"+candidate+"`: no same-repository issue found")
		case issue.open:
			open = append(open, candidate)
		}
	}
	lines := []string{"## Closing-issue audit for PR #" + number, ""}
	switch {
	case len(open) > 0:
		lines = append(lines, "The following declared closing issues remain open:")
		lines = append(lines, prAuditNumbers(open)...)
	case len(closing) > 0 && len(inspection) == 0:
		lines = append(lines, "All declared closing issues are closed.")
	case len(reasons) > 0:
		lines = append(lines, "The pull request declared that no issue was required.")
	case len(closing) == 0 && len(references) == 0:
		lines = append(lines, "No issue-tracking declaration was found.")
	}
	if len(inspection) > 0 {
		lines = append(lines, "", "Inspection errors:")
		lines = append(lines, inspection...)
	}
	if len(references) > 0 {
		lines = append(lines, "", "Non-closing references (closure requires post-merge requirement verification):")
		lines = append(lines, prAuditNumbers(references)...)
	}
	lines = append(lines, "", "This audit is read-only and never closes issues.")
	return strings.Join(lines, "\n") + "\n", nil
}

func prAuditNumbers(numbers []string) []string {
	lines := make([]string, len(numbers))
	for i, number := range numbers {
		lines[i] = "- `#" + number + "`"
	}
	return lines
}

package governance

import (
	"context"
	"errors"
	"fmt"
	"os"
	"regexp"
	"strings"
)

const issueTrackingRule = "issue-tracking"

const prTrackingSection = "related issues"
const prSummarySection = "summary"
const prVerificationSection = "test plan"

type prConfigurationError string

func (e prConfigurationError) Error() string { return string(e) }

type prBodyInput struct {
	body, repository, number string
	exempt                   bool
}

func (c *checker) prBody(ctx context.Context) (Report, error) {
	input, err := c.prBodyInput()
	if err != nil {
		return prBodyError(err)
	}
	if input.exempt && c.request.Mode != ClosingAudit {
		report := finish(nil)
		report.Text = "pr-body-guard: exempt trusted automation\n"
		return report, nil
	}
	var lookup prIssueLookup
	if c.request.IssuesFile != "" {
		lookup, err = prFixtureLookup(c.request.IssuesFile)
	} else {
		lookup, err = prGitHubLookup(input.repository, os.Getenv("GH_TOKEN"))
	}
	if err != nil {
		return prBodyError(err)
	}
	if c.request.Mode == ClosingAudit {
		text, auditErr := prOpenIssueReport(ctx, input.body, lookup, input.number)
		if auditErr != nil {
			return prBodyError(auditErr)
		}
		if c.request.SummaryFile != "" {
			if writeErr := prWriteSummary(c.request.SummaryFile, text); writeErr != nil {
				return prBodyError(writeErr)
			}
			text = ""
		}
		report := finish(nil)
		report.Text = text
		return report, nil
	}
	findings, err := validatePRBody(ctx, input.body, lookup, input.repository)
	if err != nil {
		return prBodyError(err)
	}
	return finish(findings), nil
}

func prBodyError(err error) (Report, error) {
	if _, expected := errors.AsType[prConfigurationError](err); !expected {
		return Report{}, err
	}
	report := finish([]Finding{finding("pr-body-configuration", err.Error(), "")})
	report.ExitCode = 2
	return report, nil
}

func (c *checker) prBodyInput() (prBodyInput, error) {
	name := c.request.EventPath
	if name == "" {
		name = os.Getenv("GITHUB_EVENT_PATH")
	}
	if name == "" {
		if c.request.Repository != "" || c.request.Body != "" {
			return prBodyInput{body: c.request.Body, repository: c.request.Repository, number: "unknown"}, nil
		}
		return prBodyInput{}, prConfigurationError("GITHUB_EVENT_PATH or --event-path is required")
	}
	event, err := prJSONFile(name, "event payload", false)
	if err != nil {
		return prBodyInput{}, err
	}
	pull := object(event.get("pull_request"))
	if pull == nil {
		return prBodyInput{}, prConfigurationError("event has no pull_request object")
	}
	body, ok := pull.get("body").(string)
	if !ok {
		return prBodyInput{}, prConfigurationError("event pull_request.body must be a string")
	}
	login := pythonStr(object(pull.get("user")).get("login"))
	head := pythonStr(object(pull.get("head")).get("ref"))
	exempt := login == "dependabot[bot]" || login == "release-please[bot]" || login == "github-actions[bot]" && strings.HasPrefix(head, "release-please--branches--")
	repository := object(event.get("repository")).get("full_name")
	if !truth(repository) {
		repository = os.Getenv("GITHUB_REPOSITORY")
	}
	number := "unknown"
	if pull.has("number") {
		number = pythonStr(pull.get("number"))
	}
	return prBodyInput{body, pythonStr(repository), number, exempt}, nil
}

func validatePRBody(ctx context.Context, body string, lookup prIssueLookup, repository string) ([]Finding, error) {
	if !regexp.MustCompile(`^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`).MatchString(repository) {
		return nil, prConfigurationError("repository must have owner/repository form")
	}
	cleaned := prStripIgnored(body)
	sections := prSections(cleaned)
	findings := prRequiredFindings(sections)
	if summary := sections[prSummarySection]; len(summary) == 1 && !prMeaningful(summary[0], 3) {
		findings = append(findings, finding("substantive-summary", "Summary must describe the change in non-placeholder prose.", ""))
	}
	issues, err := prTrackingFindings(ctx, sections, lookup)
	if err != nil {
		return nil, err
	}
	findings = append(findings, issues...)
	findings = append(findings, prClosingRoutes(cleaned, repository)...)
	if verification := sections[prVerificationSection]; len(verification) == 1 {
		text := regexp.MustCompile(`(?m)^[ \t]*[-*+][ \t]+\[[ xX]\].*$`).ReplaceAllString(verification[0], "")
		text = strings.TrimFunc(text, pythonWhitespace)
		if !prMeaningful(text, 2) || !prEvidence(text) {
			findings = append(findings, finding("substantive-verification", "Test Plan must record substantive commands and outcomes, or a reason a check was not run, beyond its checklist.", ""))
		}
	}
	return findings, nil
}

func prRequiredFindings(sections map[string][]string) []Finding {
	findings := []Finding{}
	for _, heading := range prRequiredSections() {
		name := strings.ToLower(heading)
		contents := sections[name]
		if len(contents) != 1 {
			findings = append(findings, finding("required-section", fmt.Sprintf("PR body must contain exactly one '## %s' section; found %d.", heading, len(contents)), ""))
		} else if contents[0] == "" && name != prSummarySection && name != prTrackingSection && name != prVerificationSection {
			findings = append(findings, finding("required-section", "'## "+heading+"' must not be empty or placeholder-only.", ""))
		}
	}
	return findings
}

func prTrackingFindings(ctx context.Context, sections map[string][]string, lookup prIssueLookup) ([]Finding, error) {
	tracking := sections[prTrackingSection]
	if len(tracking) != 1 {
		return []Finding{}, nil
	}
	content := tracking[0]
	declarations := []prIssueReference{}
	for _, keyword := range []string{"Closes", "Refs"} {
		for _, number := range prIssueNumbers(content, keyword) {
			declarations = append(declarations, prIssueReference{keyword, number})
		}
	}
	reasons := prNoIssueReasons(content)
	if len(declarations) > 0 && len(reasons) > 0 {
		return []Finding{finding(issueTrackingRule, "Related Issues must use either issue references or one 'No issue: ...' declaration, not both.", "")}, nil
	}
	if len(declarations) > 0 {
		return prVerifyDeclarations(ctx, declarations, lookup)
	}
	if len(reasons) != 1 || !prMeaningful(reasons[0], 2) {
		return []Finding{finding(issueTrackingRule, "Related Issues needs open same-repository 'Closes #N' or 'Refs #N' lines or one substantive 'No issue: ...' declaration.", "")}, nil
	}
	return []Finding{}, nil
}

func prVerifyDeclarations(ctx context.Context, declarations []prIssueReference, lookup prIssueLookup) ([]Finding, error) {
	findings := []Finding{}
	for _, declaration := range declarations {
		failure, err := prInspectIssue(ctx, declaration, lookup)
		if err != nil {
			return nil, err
		}
		if failure != nil {
			findings = append(findings, *failure)
		}
	}
	return findings, nil
}

func prClosingRoutes(body, repository string) []Finding {
	findings := []Finding{}
	section := ""
	pattern := prClosingPattern()
	for _, line := range pythonLines(body, false) {
		if heading := prHeading(line); heading != "" {
			section = heading
		}
		if section == prTrackingSection && len(prIssueNumbers(line, "Closes")) > 0 {
			continue
		}
		for _, reference := range prClosingReferences(line, repository, pattern) {
			findings = append(findings, finding(issueTrackingRule, "'"+reference+"' is a GitHub closing reference; declare closure only as a standalone 'Closes #N' line in Related Issues, or reword the mention.", ""))
		}
	}
	return findings
}

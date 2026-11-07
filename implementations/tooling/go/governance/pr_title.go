package governance

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"
)

func (c *checker) prTitle() (Report, error) {
	title, body := c.request.Title, c.request.Body
	if c.request.EventPath != "" {
		event, err := prJSONFile(c.request.EventPath, "event payload", true)
		if err != nil {
			return prTitleConfiguration(err), nil
		}
		pull := object(event.get("pull_request"))
		if pull.get(titleField) == nil {
			return prTitleConfiguration(prConfigurationError("could not resolve a PR title to validate")), nil
		}
		title, _ = pull.get(titleField).(string)
		body, _ = pull.get("body").(string)
	}
	if c.request.CommitMessagesFile != "" {
		data, err := prExplicitFile(c.request.CommitMessagesFile, "commit messages", true)
		if err != nil {
			return prTitleConfiguration(err), nil
		}
		if !utf8.Valid(data) {
			return prTitleConfiguration(errNotUTF8), nil
		}
		body += "\n\n" + strings.ReplaceAll(strings.ReplaceAll(string(data), "\r\n", "\n"), "\r", "\n")
	}
	return finish(titleFindings(title, body+"\n\n"+c.request.CommitMessages)), nil
}

func prTitleConfiguration(err error) Report {
	report := finish([]Finding{finding("pr-title-configuration", err.Error(), "")})
	report.ExitCode = 2
	return report
}

func titleFindings(title, body string) []Finding {
	findings := []Finding{}
	title = strings.TrimFunc(title, pythonWhitespace)
	if title == "" {
		return append(findings, finding("pr-title-empty", "PR title is empty.", ""))
	}
	if brandedTitle(title) {
		return append(findings, finding("pr-title-agent-brand", "PR title must not start with an agent/tool advertising prefix such as [codex], [claude], [openai], [chatgpt]. Use a project-native conventional title instead.", ""))
	}
	identities := retiredIdentities(title)
	if len(identities) > 0 {
		findings = append(findings, finding("pr-title-retired-identity", "PR title must not contain retired project naming ("+strings.Join(identities, ", ")+"). A feature PR into 'dev' is squash-merged, so this title becomes the commit release-please writes into CHANGELOG.md, where check_identity_cutover rejects it.", ""))
	}
	for _, footer := range breakingFooters(body) {
		matches := retiredIdentities(footer)
		if len(matches) > 0 {
			findings = append(findings, finding("pr-title-retired-identity", "BREAKING CHANGE footer must not contain retired project naming ("+strings.Join(matches, ", ")+"); release-please copies breaking-change footers from the squashed commit messages into CHANGELOG.md. Prose outside a footer is not checked.", ""))
			break
		}
	}
	const types = "security, added, changed, deprecated, removed, fixed, feat, fix, chore, docs, refactor, test, ci, build, perf, revert"
	shape := regexp.MustCompile(`^(?:security|added|changed|deprecated|removed|fixed|feat|fix|chore|docs|refactor|test|ci|build|perf|revert)(?:\([^()\n]+\))?!?: (.+)$`)
	match := shape.FindStringSubmatch(title)
	if match == nil {
		return append(findings, finding("pr-title-conventional", "PR title must match '<type>(<optional-scope>): <subject>' with a single type from: "+types+". Compound type prefixes (e.g. 'fix/refactor:') are rejected.", ""))
	}
	subject := match[1]
	if !regexp.MustCompile(`^[a-z].*$`).MatchString(subject) {
		findings = append(findings, finding("pr-title-subject-lowercase", fmt.Sprintf("PR title subject must start lowercase (match '^[a-z].*$'); got subject %s.", pythonRepr(subject)), ""))
	}
	return findings
}

func breakingFooters(body string) []string {
	starts := regexp.MustCompile(`(?m)^`+pythonSpace()+`*BREAKING[ -]CHANGE:`).FindAllStringIndex(body, -1)
	blocks := make([]string, 0, len(starts))
	for i, start := range starts {
		end := len(body)
		if i+1 < len(starts) {
			end = starts[i+1][0]
		}
		blocks = append(blocks, body[start[0]:end])
	}
	return blocks
}

func brandedTitle(title string) bool {
	if !strings.HasPrefix(title, "[") {
		return false
	}
	label, _, closed := strings.Cut(title[1:], "]")
	if !closed {
		return false
	}
	label = strings.TrimFunc(label, pythonWhitespace)
	// Python IGNORECASE includes dotted and dotless I in the ASCII I class.
	label = strings.Map(func(r rune) rune {
		if r == 'İ' || r == 'ı' {
			return 'i'
		}
		return r
	}, label)
	for _, brand := range []string{"codex", "claude", "openai", "chatgpt"} {
		if strings.EqualFold(label, brand) {
			return true
		}
	}
	return false
}

func retiredIdentities(text string) []string {
	seen := map[string]bool{}
	for _, bounds := range identityMatches(text, false) {
		seen[text[bounds[0]:bounds[1]]] = true
	}
	out := make([]string, 0, len(seen))
	for value := range seen {
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}

package governance

import (
	"errors"
	"io/fs"
	"maps"
	"path"
	"regexp"
	"slices"
	"strings"
)

const repoADRTemplate = adrDirectory + "/TEMPLATE.md"

func repoExists(r *repository, name string) (bool, error) {
	resolved, err := r.resolve(name)
	if err != nil {
		return false, err
	}
	_, err = r.root.Stat(resolved)
	if errors.Is(err, fs.ErrNotExist) {
		return false, nil
	}
	return err == nil, err
}

func repoChangelog(r *repository) ([]Finding, error) {
	exists, err := repoExists(r, "CHANGELOG.md")
	if err != nil || !exists {
		return []Finding{}, err
	}
	text, err := repoReadText(r, "CHANGELOG.md")
	if err != nil {
		return nil, err
	}
	headings := regexp.MustCompile(`(?m)^## \[(.+?)\]`).FindAllStringSubmatchIndex(text, -1)
	for i, heading := range headings {
		if strings.ToLower(text[heading[2]:heading[3]]) != "unreleased" {
			continue
		}
		end := len(text)
		if i+1 < len(headings) {
			end = headings[i+1][0]
		}
		if regexp.MustCompile(`(?m)^###` + pythonSpace()).MatchString(text[heading[1]:end]) {
			return []Finding{finding("changelog-unreleased-content", "CHANGELOG.md has content under [Unreleased]; assign a version number and date", "CHANGELOG.md")}, nil
		}
	}
	return []Finding{}, nil
}

func repoADRChecks(r *repository, policy *mapping, changed []string) ([]Finding, error) {
	findings := []Finding{}
	if repoADRChanged(changed) || slices.Contains(changed, "tools/policy/repo_policy.py") {
		problems, err := repoTemplate(r)
		if err != nil {
			return nil, err
		}
		findings = append(findings, problems...)
	}
	if repoADRChanged(changed) {
		problems, err := repoADRIndex(r, policy)
		if err != nil {
			return nil, err
		}
		findings = append(findings, problems...)
	}
	return findings, nil
}

func repoTemplate(r *repository) ([]Finding, error) {
	exists, err := repoExists(r, repoADRTemplate)
	if err != nil {
		return nil, err
	}
	if !exists {
		return []Finding{finding("adr-template-missing", "ADR template is missing", repoADRTemplate)}, nil
	}
	text, err := repoReadText(r, repoADRTemplate)
	if err != nil {
		return nil, err
	}
	headings := regexp.MustCompile(`(?m)^##`+pythonSpace()+`+(.+?)`+pythonSpace()+`*$`).FindAllStringSubmatch(text, -1)
	actual := map[string]bool{}
	for _, heading := range headings {
		actual[strings.TrimFunc(heading[1], pythonWhitespace)] = true
	}
	missing := []string{}
	for _, section := range []string{"Status", "Date", "Context", "Decision", "Alternatives Considered", "Consequences"} {
		if !actual[section] {
			missing = append(missing, section)
		}
	}
	if len(missing) > 0 {
		return []Finding{finding("adr-template-section-missing", "ADR template is missing required section(s): "+strings.Join(missing, ", "), repoADRTemplate)}, nil
	}
	return []Finding{}, nil
}

type repoADRRow struct{ file, title, status, date string }

func repoADRIndex(r *repository, policy *mapping) ([]Finding, error) {
	config := object(policy.get("adr_index"))
	if config == nil {
		return nil, policyInputError("adr_index must be a mapping")
	}
	index, ok := config.get("index_path").(string)
	if !ok {
		return nil, policyInputError("adr_index.index_path must be a string")
	}
	resolved, err := r.resolve(adrDirectory)
	if err != nil {
		return nil, err
	}
	names, err := fs.Glob(r.root.FS(), resolved+"/adr-*.md")
	if err != nil {
		return nil, err
	}
	expected := map[string]repoADRRow{}
	for _, name := range names {
		number, row, parseErr := repoADRFile(r, name)
		if parseErr != nil {
			return nil, parseErr
		}
		expected[number] = row
	}
	text, err := repoReadText(r, index)
	if err != nil {
		return nil, err
	}
	actual := map[string]repoADRRow{}
	rows := regexp.MustCompile(`(?m)^\| \[(\p{Nd}{3})\]\(([^)]+)\) \| (.+?) \| (.+?) \| (\p{Nd}{4}-\p{Nd}{2}-\p{Nd}{2}) \|$`).FindAllStringSubmatch(text, -1)
	for _, row := range rows {
		actual[row[1]] = repoADRRow{path.Base(strings.TrimRight(row[2], "/")), strings.TrimFunc(row[3], pythonWhitespace), repoADRStatus(row[4]), row[5]}
	}
	if !maps.Equal(expected, actual) {
		return []Finding{finding("adr-index-sync", "ADR index is out of sync with the ADR documents", index)}, nil
	}
	return []Finding{}, nil
}
func repoADRFile(r *repository, name string) (string, repoADRRow, error) {
	text, err := repoReadText(r, name)
	if err != nil {
		return "", repoADRRow{}, err
	}
	header := regexp.MustCompile(`(?m)^# ADR-(\p{Nd}{3}): (.+)$`).FindStringSubmatch(text)
	if header == nil {
		return "", repoADRRow{}, policyInputError(name + " is missing ADR header")
	}
	status, ok := markdownSection(text, "Status")
	if !ok {
		return "", repoADRRow{}, policyInputError("missing Status section")
	}
	date, ok := markdownSection(text, "Date")
	if !ok {
		return "", repoADRRow{}, policyInputError("missing Date section")
	}
	return header[1], repoADRRow{path.Base(name), strings.TrimFunc(header[2], pythonWhitespace), repoADRStatus(status), date}, nil
}
func repoADRStatus(value string) string {
	normalized := strings.Join(strings.FieldsFunc(value, pythonWhitespace), " ")
	lower := strings.ToLower(normalized)
	if slices.Contains([]string{"accepted", "proposed", deprecatedStatus}, lower) {
		return lower
	}
	if regexp.MustCompile(`^superseded by adr-\p{Nd}{3}\z`).MatchString(lower) {
		return "superseded by " + strings.ToUpper(strings.TrimPrefix(lower, "superseded by "))
	}
	return normalized
}

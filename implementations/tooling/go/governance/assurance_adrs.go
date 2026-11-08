package governance

import (
	"fmt"
	"io/fs"
	"path"
	"regexp"
	"strconv"
	"strings"
)

var assuranceADRFile = regexp.MustCompile(`^adr-([\p{Nd}]{3})-.+[.]md\z`)
var assuranceADRLevel = regexp.MustCompile(`(?m)^Classification:[` + fixedWhitespaceClass + `]*(FM[\p{Nd}]+)[` + fixedWhitespaceClass + `]*$`)
var assuranceADRArtifacts = regexp.MustCompile(`(?m)^Required artifacts:[` + fixedWhitespaceClass + `]*(.+?)[` + fixedWhitespaceClass + `]*$`)
var assuranceADRWaivers = regexp.MustCompile(`(?m)^Waivers:[` + fixedWhitespaceClass + `]*(.+?)[` + fixedWhitespaceClass + `]*$`)

func assuranceADRClassifications(r *repository, levels map[string]*mapping) ([]Finding, error) {
	findings, err := assuranceTemplateFindings(r)
	if err != nil {
		return nil, err
	}
	for _, name := range assuranceADRPaths(r) {
		number, ok := assuranceADRNumber(name)
		if !ok || number < 61 {
			continue
		}
		text, err := r.text(name)
		if err != nil {
			return nil, err
		}
		findings = append(findings, assuranceADRFields(text, name, number, levels)...)
	}
	return findings, nil
}
func assuranceTemplateFindings(r *repository) ([]Finding, error) {
	if !r.file(assuranceTemplate) {
		return []Finding{finding("adr-template-classification", "ADR template is missing", assuranceTemplate)}, nil
	}
	text, err := r.text(assuranceTemplate)
	if err != nil {
		return nil, err
	}
	missing := []string{}
	for _, snippet := range []string{"## Classification", "Classification: FM<n>", "Required artifacts:", "Waivers:"} {
		if !strings.Contains(text, snippet) {
			missing = append(missing, snippet)
		}
	}
	if len(missing) == 0 {
		return []Finding{}, nil
	}
	return []Finding{finding("adr-template-classification", "ADR template is missing FM classification field(s): "+strings.Join(missing, ", "), assuranceTemplate)}, nil
}
func assuranceADRFields(text, name string, number int, levels map[string]*mapping) []Finding {
	id := fmt.Sprintf("ADR-%03d", number)
	matches := assuranceADRLevel.FindAllStringSubmatch(text, -1)
	if len(matches) != 1 {
		return []Finding{finding("adr-classification-missing", id+" must contain exactly one 'Classification: FM<n>' field", name)}
	}
	findings := []Finding{}
	level := matches[0][1]
	if _, known := levels[level]; !known {
		findings = append(findings, finding("adr-classification-level", id+" classification level "+level+" is not defined in "+assurancePolicy, name))
	}
	fields := []struct {
		pattern       *regexp.Regexp
		rule, message string
	}{
		{assuranceADRArtifacts, "adr-classification-artifacts", " must name required artifacts delivered or waived"},
		{assuranceADRWaivers, "adr-classification-waivers", " must name waivers or explicitly say none"},
	}
	for _, field := range fields {
		match := field.pattern.FindStringSubmatch(text)
		if match == nil || !assuranceFilledField(match[1]) {
			findings = append(findings, finding(field.rule, id+field.message, name))
		}
	}
	return findings
}
func assuranceFilledField(value string) bool {
	normalized := strings.ToLower(strings.TrimFunc(value, pythonWhitespace))
	switch normalized {
	case "", "tbd", "todo", "none yet", "n/a":
		return false
	}
	return !strings.Contains(value, "<") && !strings.Contains(value, "...")
}
func assuranceADRPaths(r *repository) []string {
	root, err := r.resolve(adrDirectory)
	if err != nil {
		return []string{}
	}
	entries, err := fs.ReadDir(r.root.FS(), root)
	if err != nil {
		return []string{}
	}
	result := []string{}
	for _, entry := range entries {
		if match, _ := path.Match("adr-*.md", entry.Name()); match {
			result = append(result, path.Join(adrDirectory, entry.Name()))
		}
	}
	return result
}
func assuranceADRNumber(name string) (int, bool) {
	match := assuranceADRFile.FindStringSubmatch(path.Base(name))
	if match == nil {
		return 0, false
	}
	normalized, ok := pythonIntegerText(match[1])
	if !ok {
		return 0, false
	}
	number, err := strconv.Atoi(normalized)
	return number, err == nil
}

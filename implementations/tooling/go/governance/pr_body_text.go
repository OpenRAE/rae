package governance

import (
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"

	"golang.org/x/text/cases"
)

func prRequiredSections() []string {
	return []string{"Summary", "Requirement UIDs", "Related Issues", "ADR Impact", "Changes", "Test Plan", "Ground Control Checks", "Traceability", "Checklist"}
}

func prStripIgnored(text string) string {
	text = regexp.MustCompile(`(?s)<!--.*?-->`).ReplaceAllString(text, "")
	marker := regexp.MustCompile("^[ \\t]*(`{3,}|~{3,})")
	kept := []string{}
	var fence byte
	width := 0
	for _, line := range pythonLines(text, false) {
		match := marker.FindStringSubmatch(line)
		if fence == 0 {
			if match == nil {
				kept = append(kept, line)
			} else {
				fence, width = match[1][0], len(match[1])
			}
			continue
		}
		if match != nil && match[1][0] == fence && len(match[1]) >= width {
			fence = 0
		}
	}
	return strings.Join(kept, "\n")
}

func prHeading(line string) string {
	if len(line) < 3 || !strings.HasPrefix(line, "##") || line[2] != ' ' && line[2] != '\t' {
		return ""
	}
	return cases.Fold().String(strings.TrimFunc(line[3:], pythonWhitespace))
}

func prSections(text string) map[string][]string {
	sections := map[string][]string{}
	current := ""
	lines := []string{}
	for _, line := range pythonLines(text, false) {
		name := prHeading(line)
		if name == "" {
			lines = append(lines, line)
			continue
		}
		if current != "" {
			sections[current] = append(sections[current], strings.TrimFunc(strings.Join(lines, "\n"), pythonWhitespace))
		}
		current, lines = name, nil
	}
	if current != "" {
		sections[current] = append(sections[current], strings.TrimFunc(strings.Join(lines, "\n"), pythonWhitespace))
	}
	return sections
}

func prMeaningful(text string, minimumWords int) bool {
	// Fixed phrases include dotted and dotless I from the reference's
	// case-insensitive spelling.
	placeholder := regexp.MustCompile(`(?i)(?:todo|tbd|placeholder|n/?a)|br[iİı]ef descr[iİı]pt[iİı]on|add (?:context|deta[iİı]ls)|descr[iİı]be (?:the )?(?:problem|f[iİı]x|ver[iİı]f[iİı]cat[iİı]on)|#(?:xx|n)`)
	var out strings.Builder
	previous := 0
	for offset := 0; offset < len(text); {
		bounds := placeholder.FindStringIndex(text[offset:])
		if bounds == nil {
			break
		}
		start, end := bounds[0]+offset, bounds[1]+offset
		if !prPlaceholder(text, start, end) {
			offset = start + 1
			continue
		}
		out.WriteString(text[previous:start])
		out.WriteByte(' ')
		previous, offset = end, end
	}
	out.WriteString(text[previous:])
	remaining := strings.NewReplacer("*", "", "_", "", "`", "", "#", "").Replace(out.String())
	remaining = strings.TrimFunc(remaining, pythonWhitespace)
	words := regexp.MustCompile(`[A-Za-z0-9][A-Za-z0-9'/-]*`).FindAllStringIndex(remaining, -1)
	return pythonStringLength(remaining) >= 12 && len(words) >= minimumWords
}

func prPlaceholder(text string, start, end int) bool {
	match := text[start:end]
	if strings.HasPrefix(match, "#") {
		return !prWordAfter(text, end)
	}
	return strings.ContainsRune(match, ' ') || prWordBounds(text, start, end)
}

func prEvidence(text string) bool {
	if regexp.MustCompile("`[^`]+`").MatchString(text) {
		return true
	}
	hint := regexp.MustCompile(`(?i)(?:pass(?:ed|es)?|test(?:ed|s)?|ver[iİı]fy|ver[iİı]f[iİı]ed|ver[iİı]f[iİı]cat[iİı]on|nox|pytest|ruff|mypy|manual(?:ly)?|not run|not appl[iİı]cable|bu[iİı]ld|smoke)`)
	for _, bounds := range hint.FindAllStringIndex(text, -1) {
		if prWordBounds(text, bounds[0], bounds[1]) {
			return true
		}
	}
	return false
}

func prWordBounds(text string, start, end int) bool {
	if start > 0 {
		before, _ := utf8.DecodeLastRuneInString(text[:start])
		if prWordRune(before) {
			return false
		}
	}
	return !prWordAfter(text, end)
}

func prWordAfter(text string, end int) bool {
	if end == len(text) {
		return false
	}
	after, _ := utf8.DecodeRuneInString(text[end:])
	return prWordRune(after)
}

func prWordRune(value rune) bool {
	return value == '_' || unicode.IsLetter(value) || unicode.IsNumber(value)
}

func prClosingPattern() *regexp.Regexp {
	repository := `[A-Za-z0-9_.İı-]+/[A-Za-z0-9_.İı-]+`
	return regexp.MustCompile(`(?i)(?:close[sd]?|f[iİı]x(?:e[sd])?|resolve[sd]?)(?::[ \t]*|[ \t]+)(?:#\p{Nd}+|(` + repository + `)#\p{Nd}+|https?://g[iİı]thub\.com/(` + repository + `)/[iİı]ssues/\p{Nd}+)`)
}

func prClosingReferences(text, repository string, pattern *regexp.Regexp) []string {
	result := []string{}
	for _, match := range pattern.FindAllStringSubmatchIndex(text, -1) {
		if !prWordBounds(text, match[0], match[1]) {
			continue
		}
		selected := ""
		for _, group := range []int{2, 4} {
			if match[group] >= 0 {
				selected = text[match[group]:match[group+1]]
			}
		}
		if selected != "" && !prRepositoryEqual(selected, repository) {
			continue
		}
		result = append(result, text[match[0]:match[1]])
	}
	return result
}

func prRepositoryEqual(actual, expected string) bool {
	actual = strings.Map(func(r rune) rune {
		if r == 'İ' || r == 'ı' {
			return 'i'
		}
		return r
	}, actual)
	return strings.EqualFold(actual, expected)
}

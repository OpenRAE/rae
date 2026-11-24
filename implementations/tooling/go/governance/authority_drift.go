package governance

import (
	"regexp"
	"slices"
	"strings"
	"unicode"
	"unicode/utf8"
)

var boundaryReadmeLink = regexp.MustCompile(`\(([^)]+)\)`)
var boundaryReadmeCode = regexp.MustCompile("`([^`\n]+)`")

func boundaryDriftText(r *repository, name, rule string) (string, []Finding) {
	if !r.file(name) {
		return "", []Finding{finding(rule, name+" is missing", name)}
	}
	text, err := r.text(name)
	if err != nil {
		return "", []Finding{finding(rule, name+" could not be read", name)}
	}
	return text, []Finding{}
}
func boundaryADRDrift(r *repository, roots []boundaryRoot) []Finding {
	original, findings := boundaryDriftText(r, boundaryADR, "authority-boundary-adr-missing")
	seam, seamFindings := boundaryDriftText(r, boundarySeamADR, "authority-boundary-seam-adr-missing")
	findings = append(findings, seamFindings...)
	if len(findings) == 2 {
		return findings
	}
	union := original + "\n" + seam
	for _, entry := range roots {
		if !boundaryMention(union, entry.family) {
			findings = append(findings, finding("authority-boundary-adr-drift", "neither "+boundaryADR+" nor "+boundarySeamADR+" mentions authority family '"+entry.family+"' (root='"+entry.root+"', id="+pythonRepr(entry.id)+"); the immutable ADR pair must reference every authority family or it has drifted", boundaryADR))
		}
	}
	return findings
}

func boundaryReadmeDrift(r *repository, name, kind string) []Finding {
	text, findings := boundaryDriftText(r, name, "authority-boundary-"+kind+"-readme-missing")
	if len(findings) > 0 {
		return findings
	}
	accepted := []string{boundaryPolicy, "authority/authority-boundary.yaml"}
	if kind == "contracts" {
		accepted[1] = "../specs/authority/authority-boundary.yaml"
	}
	tokens := []string{}
	for _, pattern := range []*regexp.Regexp{boundaryReadmeLink, boundaryReadmeCode} {
		for _, match := range pattern.FindAllStringSubmatch(text, -1) {
			tokens = append(tokens, match[1])
		}
	}
	rule := "authority-boundary-" + kind + "-readme-drift"
	if !slices.ContainsFunc(accepted, func(token string) bool { return slices.Contains(tokens, token) }) {
		findings = append(findings, finding(rule, name+" must reference the canonical authority manifest at one of "+pythonRepr(accepted)+" as a Markdown link target or inline-code token; a partial-substring like 'old/authority-boundary.yaml' does not satisfy this check", name))
	}
	if !boundaryMention(text, "ADR-019") {
		findings = append(findings, finding(rule, name+" must reference ADR-019 (canonical-seam ADR)", name))
	}
	return findings
}

func boundaryMention(text, token string) bool {
	if token == "" {
		return false
	}
	for offset := 0; offset < len(text); {
		index := strings.Index(text[offset:], token)
		if index < 0 {
			return false
		}
		start := offset + index
		end := start + len(token)
		before, _ := utf8.DecodeLastRuneInString(text[:start])
		after, _ := utf8.DecodeRuneInString(text[end:])
		if !boundaryWord(before) && !boundaryWord(after) {
			return true
		}
		offset = start + 1
	}
	return false
}
func boundaryWord(r rune) bool { return pythonWord(r) && (r == '_' || unicode.Is(pythonAssigned(), r)) }

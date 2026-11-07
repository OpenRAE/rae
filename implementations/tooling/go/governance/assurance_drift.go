package governance

import (
	"strings"
	"unicode/utf8"
)

const assurancePolicyRulePrefix = "assurance-policy-"

type assuranceTarget struct{ id, name string }

func assuranceDrift(r *repository, levels []any) ([]Finding, error) {
	byID := assuranceByID(levels)
	baseline := []assuranceTarget{}
	for _, id := range assuranceCanonicalIDs() {
		name, _ := byID[id].get(nameField).(string)
		baseline = append(baseline, assuranceTarget{id, name})
	}
	extended := []assuranceTarget{}
	named := false
	for _, value := range levels {
		level := object(value)
		id, idOK := level.get("id").(string)
		name, nameOK := level.get(nameField).(string)
		if idOK && nameOK {
			extended = append(extended, assuranceTarget{id, name})
			named = named || name != ""
		}
	}
	if !named {
		extended = baseline
	}
	findings := []Finding{}
	for _, target := range []struct {
		path, kind string
		levels     []assuranceTarget
	}{{assuranceADR, "adr", baseline}, {assuranceCoding, "coding-standards", extended}, {assuranceOverview, "formal-overview", extended}} {
		problems, err := assuranceDocumentDrift(r, target.path, target.kind, target.levels)
		if err != nil {
			return nil, err
		}
		findings = append(findings, problems...)
	}
	_, required := assuranceRequired(levels)
	for _, target := range [][2]string{{assuranceCoding, "coding-standards"}, {assuranceOverview, "formal-overview"}} {
		problems, err := assuranceKeywordDrift(r, target[0], target[1], required)
		if err != nil {
			return nil, err
		}
		findings = append(findings, problems...)
	}
	return findings, nil
}

func assuranceDocumentDrift(r *repository, name, kind string, targets []assuranceTarget) ([]Finding, error) {
	if !r.file(name) {
		return []Finding{finding(assurancePolicyRulePrefix+kind+"-missing", name+" is missing — the policy references it", name)}, nil
	}
	text, err := r.text(name)
	if err != nil {
		return nil, err
	}
	normalized := strings.Join(strings.FieldsFunc(text, pythonWhitespace), " ")
	missingIDs, missingNames, unpaired := []string{}, []string{}, []string{}
	for _, target := range targets {
		hasID := strings.Contains(text, target.id)
		if !hasID {
			missingIDs = append(missingIDs, target.id)
		}
		canonical := strings.Join(strings.FieldsFunc(target.name, pythonWhitespace), " ")
		hasName := strings.Contains(normalized, canonical)
		if canonical != "" && !hasName {
			missingNames = append(missingNames, target.name)
		}
		if canonical != "" && hasID && hasName && !assuranceIDNamePaired(normalized, target.id, canonical) {
			unpaired = append(unpaired, target.id+"↔"+pythonRepr(target.name))
		}
	}
	rule := assurancePolicyRulePrefix + kind + "-drift"
	findings := []Finding{}
	if len(missingIDs) > 0 {
		findings = append(findings, finding(rule, name+" no longer mentions every canonical level id; missing: "+pythonRepr(missingIDs), name))
	}
	if len(missingNames) > 0 {
		findings = append(findings, finding(rule, name+" no longer mentions every canonical level name; missing: "+pythonRepr(missingNames), name))
	}
	if len(unpaired) > 0 {
		findings = append(findings, finding(rule, name+" mentions every canonical id and name, but at least one (id, name) pair is not co-located within a 200-character window — likely id/name drift: "+strings.Join(unpaired, ", "), name))
	}
	return findings, nil
}

func assuranceIDNamePaired(text, id, name string) bool {
	runes := []rune(text)
	idLength := utf8.RuneCountInString(id)
	offset, runeOffset := 0, 0
	for offset <= len(text) {
		index := strings.Index(text[offset:], id)
		if index < 0 {
			return false
		}
		position := offset + index
		runeIndex := runeOffset + utf8.RuneCountInString(text[offset:position])
		if strings.Contains(string(runes[max(0, runeIndex-40):min(len(runes), runeIndex+idLength+40)]), name) {
			return true
		}
		if position == len(text) {
			return false
		}
		_, width := utf8.DecodeRuneInString(text[position:])
		offset, runeOffset = position+width, runeIndex+1
	}
	return false
}

func assuranceKeywordDrift(r *repository, name, kind string, required []string) ([]Finding, error) {
	if !r.file(name) {
		return []Finding{}, nil
	}
	text, err := r.text(name)
	if err != nil {
		return nil, err
	}
	// Only ASCII keyword substrings are asserted. Preserve the full lowercase
	// expansion that could otherwise turn dotted capital I into plain ASCII i.
	text = strings.ToLower(strings.ReplaceAll(text, "İ", "i\u0307"))
	keywords := map[string][]string{
		unitTestsArtifact: {"unit tests"}, invariantArtifact: {"invariant"},
		contractCoverageArtifact:       {"typed ir", "contract coverage", "typed ir/contract"},
		differentialArtifact:           {"property-based", "differential test"},
		"abstract_state_machine_model": {"abstract state-machine", "state-machine model"},
	}
	missing := []string{}
	for _, slug := range required {
		variants, known := keywords[slug]
		if !known {
			continue
		}
		found := false
		for _, variant := range variants {
			found = found || strings.Contains(text, variant)
		}
		if !found {
			missing = append(missing, slug)
		}
	}
	if len(missing) == 0 {
		return []Finding{}, nil
	}
	return []Finding{finding(assurancePolicyRulePrefix+kind+"-drift", name+" no longer mentions every required artifact; missing keywords for: "+pythonRepr(missing), name)}, nil
}

package governance

import (
	"fmt"
	"path"
	"path/filepath"
	"regexp"
	"slices"
	"strconv"
	"strings"
)

var assuranceLedgerADR = regexp.MustCompile(`^ADR-[` + pythonSchemaDigits() + `]{3}\z`)

func ledgerFinding(rule, message string) Finding {
	return finding("fm-classification-ledger-"+rule, message, assuranceLedger)
}

func assuranceLedgerFindings(r *repository, levels []any) ([]Finding, error) {
	raw, findings, err := assuranceYAML(r, assuranceLedger, "fm-classification-ledger", "FM classification ledger")
	if err != nil || raw == nil {
		return findings, err
	}
	if raw.get("ledger") != "per-change-fm-classification" {
		findings = append(findings, ledgerFinding("field", "ledger field must be 'per-change-fm-classification'"))
	}
	if raw.get("policy_ref") != assurancePolicy {
		findings = append(findings, ledgerFinding("policy-ref", "policy_ref must be "+assurancePolicy))
	}
	entries, ok := raw.get("entries").([]any)
	if !ok {
		return append(findings, ledgerFinding("field", "entries must be a YAML list")), nil
	}
	required, kinds := assuranceRequired(levels)
	seen := []string{}
	paths := assuranceADRPaths(r)
	for i, value := range entries {
		entry := object(value)
		if entry == nil {
			findings = append(findings, ledgerFinding("entry", "entries["+strconv.Itoa(i)+"] must be a mapping"))
			continue
		}
		entryID, added, identityFindings := assuranceLedgerIdentity(entry, i, seen, paths)
		if added != nil {
			seen = append(seen, *added)
		}
		findings = append(findings, identityFindings...)
		problems, entryErr := assuranceLedgerEntry(r, entryID, entry, required, kinds)
		if entryErr != nil {
			return nil, entryErr
		}
		findings = append(findings, problems...)
	}
	runtime := assuranceRuntimeADRs(paths)
	if missing := stringDifference(runtime, seen); len(missing) > 0 {
		findings = append(findings, ledgerFinding("coverage", "ledger must cover existing runtime-surface ADRs 023-058; missing: "+pythonRepr(missing)))
	}
	return findings, nil
}

func assuranceLedgerIdentity(entry *mapping, i int, seen, paths []string) (string, *string, []Finding) {
	findings := []Finding{}
	var added *string
	id, ok := entry.get("adr").(string)
	switch {
	case !ok || !assuranceLedgerADR.MatchString(id):
		findings = append(findings, ledgerFinding("entry", "entries["+strconv.Itoa(i)+"].adr must be an ADR-NNN id"))
	case slices.Contains(seen, id):
		findings = append(findings, ledgerFinding("duplicate", "ledger contains duplicate entry for "+id))
	default:
		added = &id
		prefix := "adr-" + strings.TrimPrefix(id, "ADR-") + "-"
		if !slices.ContainsFunc(paths, func(name string) bool { return strings.HasPrefix(path.Base(name), prefix) }) {
			findings = append(findings, ledgerFinding("entry", id+" does not resolve to an ADR file under "+adrDirectory))
		}
	}
	entryID := id
	if !ok {
		entryID = "entries[" + strconv.Itoa(i) + "]"
	}
	return entryID, added, findings
}

func assuranceLedgerEntry(r *repository, id string, entry *mapping, required map[string][]string, kinds []string) ([]Finding, error) {
	findings := []Finding{}
	if !assuranceNonblank(entry.get("surface")) {
		findings = append(findings, ledgerFinding("entry", id+".surface must be non-empty"))
	}
	level, levelText := entry.get("fm_level").(string)
	obligation, known := required[level]
	if !levelText || !known {
		findings = append(findings, ledgerFinding("level", id+".fm_level "+pythonRepr(entry.get("fm_level"))+" is not defined in "+assurancePolicy))
		obligation = []string{}
	}
	delivered, ok := entry.get("delivered_artifacts").([]any)
	if !ok {
		findings = append(findings, ledgerFinding("artifact", id+".delivered_artifacts must be a YAML list"))
	}
	satisfied := []string{}
	for i, artifact := range delivered {
		kind, problems, err := assuranceLedgerArtifact(r, id, i, artifact, kinds)
		if err != nil {
			return nil, err
		}
		if kind != nil {
			satisfied = append(satisfied, *kind)
		}
		findings = append(findings, problems...)
	}
	waived, problems := assuranceLedgerWaivers(id, entry, kinds)
	satisfied = append(satisfied, waived...)
	findings = append(findings, problems...)
	if missing := stringDifference(obligation, satisfied); len(missing) > 0 {
		findings = append(findings, ledgerFinding("artifacts", id+" ("+level+") must deliver or waive required artifact kind(s): "+pythonRepr(missing)))
	}
	return findings, nil
}

func assuranceLedgerWaivers(id string, entry *mapping, kinds []string) ([]string, []Finding) {
	findings := []Finding{}
	satisfied := []string{}
	var waived []any
	if entry.has("waived_artifacts") {
		var ok bool
		waived, ok = entry.get("waived_artifacts").([]any)
		if !ok {
			findings = append(findings, ledgerFinding("waiver", id+".waived_artifacts must be a YAML list when present"))
		}
	}
	for i, waiver := range waived {
		kind, problems := assuranceLedgerWaiver(id, i, waiver, kinds)
		if kind != nil {
			satisfied = append(satisfied, *kind)
		}
		findings = append(findings, problems...)
	}
	return satisfied, findings
}

func assuranceLedgerArtifact(r *repository, id string, index int, value any, kinds []string) (*string, []Finding, error) {
	prefix := id + " delivered_artifacts[" + strconv.Itoa(index) + "]"
	item := object(value)
	if item == nil {
		return nil, []Finding{ledgerFinding("artifact", prefix+" must be a mapping")}, nil
	}
	kind, kindText := item.get("kind").(string)
	findings := []Finding{}
	if !kindText || !slices.Contains(kinds, kind) {
		findings = append(findings, ledgerFinding("artifact", prefix+".kind must be one of "+pythonRepr(kinds)+"; got "+pythonRepr(item.get("kind"))))
	}
	if !assuranceNonblank(item.get("path")) {
		findings = append(findings, ledgerFinding("artifact", prefix+".path must be a non-empty repo-relative path"))
	} else {
		selected := pythonStr(item.get("path"))
		relative, contained, err := assuranceLedgerPath(r, selected)
		if err != nil {
			return nil, nil, err
		}
		if !contained {
			findings = append(findings, ledgerFinding("artifact", id+" delivered artifact path escapes the repo root: "+selected))
		} else if _, statErr := r.root.Stat(relative); statErr != nil {
			findings = append(findings, ledgerFinding("artifact", id+" delivered artifact path does not exist: "+selected))
		}
	}
	if kindText {
		return &kind, findings, nil
	}
	return nil, findings, nil
}

func assuranceLedgerPath(r *repository, selected string) (string, bool, error) {
	absolute, err := documentPath(r.absolute, selected)
	if err != nil {
		return "", false, err
	}
	if !containedDocumentPath(r.absolute, absolute) {
		return "", false, nil
	}
	relative, err := filepath.Rel(r.absolute, absolute)
	return relative, err == nil, err
}

func assuranceLedgerWaiver(id string, index int, value any, kinds []string) (*string, []Finding) {
	prefix := id + " waived_artifacts[" + strconv.Itoa(index) + "]"
	item := object(value)
	if item == nil {
		return nil, []Finding{ledgerFinding("waiver", prefix+" must be a mapping")}
	}
	kind, textual := item.get("kind").(string)
	findings := []Finding{}
	if !textual || !slices.Contains(kinds, kind) {
		findings = append(findings, ledgerFinding("waiver", prefix+".kind must be one of "+pythonRepr(kinds)+"; got "+pythonRepr(item.get("kind"))))
	}
	if !assuranceNonblank(item.get("rationale")) {
		findings = append(findings, ledgerFinding("waiver", prefix+".rationale must be non-empty"))
	}
	if textual {
		return &kind, findings
	}
	return nil, findings
}
func assuranceNonblank(value any) bool {
	text, ok := value.(string)
	return ok && strings.TrimFunc(text, pythonWhitespace) != ""
}

func assuranceRuntimeADRs(paths []string) []string {
	runtime := []string{}
	for _, name := range paths {
		if number, ok := assuranceADRNumber(name); ok && number >= 23 && number < 59 {
			runtime = append(runtime, fmt.Sprintf("ADR-%03d", number))
		}
	}
	return runtime
}

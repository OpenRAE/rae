package arch

import (
	"fmt"
	"io/fs"
	"maps"
	"slices"
	"strings"
)

// The rules of ADR-122.
const (
	ruleModules         = "ARCH-001"
	ruleLayers          = "ARCH-002"
	rulePackages        = "ARCH-003"
	ruleDeclaredImports = "ARCH-004"
	ruleClassified      = "ARCH-005"
	ruleCodeImports     = "ARCH-006"
	ruleTestImports     = "ARCH-007"
	ruleExternal        = "ARCH-008"
	ruleTable           = "ARCH-009"
	ruleNoCycles        = "ARCH-010"
	ruleInternal        = "ARCH-011"
	ruleExported        = "ARCH-012"
)

// The checks that enforce the rules.
const (
	byArchcheck = "archcheck"
	byCompiler  = "go build"
)

// rules maps each rule of ADR-122 to the check that enforces it.
func rules() map[string]string {
	return map[string]string{
		ruleModules:         byArchcheck,
		ruleLayers:          byArchcheck,
		rulePackages:        byArchcheck,
		ruleDeclaredImports: byArchcheck,
		ruleClassified:      byArchcheck,
		ruleCodeImports:     byArchcheck,
		ruleTestImports:     byArchcheck,
		ruleExternal:        byArchcheck,
		ruleTable:           byArchcheck,
		ruleNoCycles:        byCompiler,
		ruleInternal:        byCompiler,
		ruleExported:        byCompiler,
	}
}

// CheckRules checks that the rule table of the ADR in name states each rule
// that a check enforces, and that it maps each rule to that check. A row of
// the table has three cells: the rule ID, the statement, and the check in
// backquotes.
func CheckRules(fsys fs.FS, name string) ([]Finding, error) {
	content, err := fs.ReadFile(fsys, name)
	if err != nil {
		return nil, err
	}
	want := rules()
	var findings []Finding
	for line := range strings.Lines(string(content)) {
		cells := strings.Split(strings.TrimSpace(line), "|")
		if len(cells) != 5 || !strings.HasPrefix(strings.TrimSpace(cells[1]), "ARCH-") {
			continue
		}
		id := strings.TrimSpace(cells[1])
		check := strings.Trim(strings.TrimSpace(cells[3]), "`")
		enforced, ok := want[id]
		delete(want, id)
		if !ok {
			findings = append(findings, Finding{
				Rule: ruleTable, Location: name,
				Problem: fmt.Sprintf("the table states rule %s, which no check enforces, or states it again.", id),
				Fix:     "add a check for the rule, or remove the row.",
			})
			continue
		}
		if check != enforced {
			findings = append(findings, Finding{
				Rule: ruleTable, Location: name,
				Problem: fmt.Sprintf("the table maps rule %s to %q, but %q enforces it.", id, check, enforced),
				Fix:     fmt.Sprintf("set the check of rule %s to %q.", id, enforced),
			})
		}
	}
	for _, id := range slices.Sorted(maps.Keys(want)) {
		findings = append(findings, Finding{
			Rule: ruleTable, Location: name,
			Problem: fmt.Sprintf("a check enforces rule %s, which the table does not state.", id),
			Fix:     "add the rule to the table.",
		})
	}
	return findings, nil
}

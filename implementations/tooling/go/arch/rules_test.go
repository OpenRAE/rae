package arch

import (
	"fmt"
	"maps"
	"slices"
	"strings"
	"testing"
	"testing/fstest"
)

// tableOf returns an ADR rule table that states each rule with its check.
func tableOf(checks map[string]string) string {
	var table strings.Builder
	table.WriteString("| Rule | Statement | Check |\n| --- | --- | --- |\n")
	for _, id := range slices.Sorted(maps.Keys(checks)) {
		fmt.Fprintf(&table, "| %s | A statement. | `%s` |\n", id, checks[id])
	}
	return table.String()
}

type ruleCase struct {
	name    string
	table   string
	problem string
}

// ruleCases returns one rule table for each way in which a table can break
// ARCH-009, with the finding that the table causes.
func ruleCases() []ruleCase {
	missing := rules()
	delete(missing, "ARCH-005")
	extra := rules()
	extra["ARCH-099"] = byArchcheck
	wrong := rules()
	wrong["ARCH-010"] = byArchcheck
	return []ruleCase{
		{"rule without a row", tableOf(missing), "ARCH-005, which the table does not state"},
		{"row without a check", tableOf(extra), "ARCH-099, which no check enforces"},
		{"row with another check", tableOf(wrong), `rule ARCH-010 to "archcheck", but "go build"`},
		{"duplicate row", tableOf(rules()) + "| ARCH-001 | Again. | `archcheck` |\n", "ARCH-001, which no check enforces, or states it again"},
	}
}

func TestCheckRulesAcceptsATableThatMatchesTheChecks(t *testing.T) {
	fsys := fstest.MapFS{"adr.md": {Data: []byte("# ADR\n\n" + tableOf(rules()) + "\nText | with ARCH-001 | pipes.\n")}}
	findings, err := CheckRules(fsys, "adr.md")
	if err != nil {
		t.Fatalf("CheckRules() error = %v", err)
	}
	if len(findings) != 0 {
		t.Errorf("CheckRules() = %v, want no findings", findings)
	}
}

func TestCheckRulesReportsEachMismatch(t *testing.T) {
	for _, test := range ruleCases() {
		t.Run(test.name, func(t *testing.T) {
			findings, err := CheckRules(fstest.MapFS{"adr.md": {Data: []byte(test.table)}}, "adr.md")
			if err != nil {
				t.Fatalf("CheckRules() error = %v", err)
			}
			if !hasFinding(findings, "ARCH-009", test.problem) {
				t.Errorf("CheckRules() = %v, want an ARCH-009 finding about %q with a fix", findings, test.problem)
			}
		})
	}
}

func TestCheckRulesReportsAMissingADR(t *testing.T) {
	if _, err := CheckRules(fstest.MapFS{}, "adr.md"); err == nil {
		t.Error("CheckRules() error = nil, want an error")
	}
}

// TestEachRuleHasItsCheck fails when a rule that archcheck enforces has no
// tested finding, or when archcheck reports a rule that the compiler enforces.
func TestEachRuleHasItsCheck(t *testing.T) {
	tested := map[string]bool{}
	for _, test := range designCases() {
		tested[test.rule] = true
	}
	for _, test := range codeCases() {
		tested[test.rule] = true
	}
	for range ruleCases() {
		tested["ARCH-009"] = true
	}
	checks := rules()
	for id, check := range checks {
		if got, want := tested[id], check == byArchcheck; got != want {
			t.Errorf("rule %s with check %q: tested = %t, want %t", id, check, got, want)
		}
	}
	for id := range tested {
		if _, ok := checks[id]; !ok {
			t.Errorf("the tests report rule %s, which rules() does not list", id)
		}
	}
}

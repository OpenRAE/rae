package governance

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/tooling/go/arch"
	"github.com/google/go-cmp/cmp"
)

func TestReferenceParity(t *testing.T) {
	encoded, err := os.ReadFile("testdata/reference-cases.hex")
	if err != nil {
		t.Fatal(err)
	}
	data, err := hex.DecodeString(strings.TrimSpace(string(encoded)))
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name     string
		Request  Request
		Findings []Finding
	}
	if err := json.Unmarshal(data, &cases); err != nil {
		t.Fatal(err)
	}
	if len(cases) == 0 {
		t.Fatal("reference fixture inventory is empty")
	}
	for _, tc := range cases {
		t.Run(tc.Name, func(t *testing.T) {
			report, err := Check(context.Background(), tc.Request)
			if err != nil {
				t.Fatalf("Check(%s) error = %v, want the recorded reference verdict", tc.Name, err)
			}
			if diff := cmp.Diff(tc.Findings, report.Findings); diff != "" {
				t.Errorf("Check(%s) findings mismatch (-want +got):\n%s", tc.Name, diff)
			}
			want := 0
			if len(tc.Findings) > 0 {
				want = 1
			}
			if report.ExitCode != want {
				t.Errorf("Check(%s) exit = %d, want %d", tc.Name, report.ExitCode, want)
			}
		})
	}
}

func TestLimitsSecurityAndErrors(t *testing.T) {
	report, err := Check(context.Background(), Request{Tool: "repo-policy", Root: "../../../..", Paths: []string{"../outside"}})
	if err != nil {
		t.Fatalf("Check(repo-policy) error = %v, want a machine-readable unsafe-path refusal", err)
	}
	for _, finding := range report.Findings {
		if finding.RuleID == "policy-path-unsafe" {
			return
		}
	}
	t.Fatalf("Check(repo-policy) findings = %v, want policy-path-unsafe", report.Findings)
}

func TestDefectRegressions(t *testing.T) {
	report, err := Check(context.Background(), Request{Tool: "pr-title", Title: "feat: preserve names", CommitMessages: "feat: preserve names\n\nBREAKING CHANGE: update clients\nA" + "CES clients must migrate"})
	if err != nil {
		t.Fatalf("Check(pr-title) error = %v, want an evaluated breaking-change verdict", err)
	}
	for _, finding := range report.Findings {
		if finding.RuleID == "pr-title-retired-identity" {
			return
		}
	}
	t.Fatalf("Check(pr-title) findings = %v, want pr-title-retired-identity", report.Findings)
}

func TestPinnedAuthority(t *testing.T) {
	report, err := Check(context.Background(), Request{Tool: "adr-immutability", Root: t.TempDir()})
	if err != nil {
		t.Fatalf("Check(adr-immutability) error = %v, want a manifest finding", err)
	}
	if len(report.Findings) == 0 {
		t.Fatal("Check(adr-immutability) has no findings, want a missing-manifest refusal")
	}
}

func TestDeclaredDesign(t *testing.T) {
	// Chronology is established by the design commit and recorded native check,
	// while this test exercises the real model's enforcement on a violated edge.
	root, err := os.OpenRoot("../../../..")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = root.Close() }()
	model, err := arch.Load(root.FS(), "implementations/architecture.json")
	if err != nil {
		t.Fatal(err)
	}
	if findings := model.CheckDesign(); len(findings) != 0 {
		t.Fatalf("CheckDesign() = %v, want no findings", findings)
	}
	found := false
	for i, pkg := range model.Packages {
		if pkg.Dir == "implementations/tooling/go/governance" {
			model.Packages[i].Imports = append(model.Packages[i].Imports, pkg.Dir)
			found = true
			break
		}
	}
	if !found {
		t.Fatal("governance package has no declared design")
	}
	if findings := model.CheckDesign(); len(findings) == 0 {
		t.Fatal("CheckDesign() accepts a self import, want an architecture finding")
	}
}

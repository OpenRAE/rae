package governance

import (
	"context"
	"os"
	"strings"
	"testing"
)

func TestReferenceParity(t *testing.T) {
	// Both reference title outcomes are deterministic and need no repository.
	for _, title := range []string{"feat: preserve contract authority", "Fix: Invalid title"} {
		report, err := Check(context.Background(), Request{Tool: "pr-title", Title: title})
		if err != nil {
			t.Fatalf("Check(pr-title) error = %v, want an evaluated title verdict", err)
		}
		if (len(report.Findings) == 0) != (title == "feat: preserve contract authority") {
			t.Errorf("Check(pr-title) findings = %v, want the reference verdict for %q", report.Findings, title)
		}
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
	// Issue #908: breaking-change footers, including continuation lines,
	// reach the changelog and must reject retired project naming.
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
	// A missing manifest is a policy failure, never a verified empty ADR set.
	report, err := Check(context.Background(), Request{Tool: "adr-immutability", Root: t.TempDir()})
	if err != nil {
		t.Fatalf("Check(adr-immutability) error = %v, want a manifest finding", err)
	}
	if len(report.Findings) == 0 {
		t.Fatal("Check(adr-immutability) has no findings, want a missing-manifest refusal")
	}
}

func TestDeclaredDesign(t *testing.T) {
	// The design is independently validated before implementation. The Go
	// repository-policy integration must also accept the declared repository.
	report, err := Check(context.Background(), Request{Tool: "repo-policy", Root: "../../../.."})
	if err != nil {
		t.Fatalf("Check(repo-policy) error = %v, want an evaluated declared-model verdict", err)
	}
	if len(report.Findings) != 0 {
		t.Fatalf("Check(repo-policy) findings = %v, want the declared repository to pass", report.Findings)
	}
}

func TestBaseRevisionGuard(t *testing.T) {
	// The production workflow must select the trusted base before it executes
	// a Go guard. The implementation adds the executable sentinel fixture.
	workflow, err := os.ReadFile("../../../../.github/workflows/pr-body-policy.yml")
	if err != nil {
		t.Fatal(err)
	}
	text := string(workflow)
	if !strings.Contains(text, "ref: ${{ github.event.pull_request.base.sha }}") || !strings.Contains(text, "./cmd/policycheck") {
		t.Fatal("PR body workflow lacks the base-revision Go guard")
	}
}

func TestHostedGates(t *testing.T) {
	workflow, err := os.ReadFile("../../../../.github/workflows/canonical-verification.yml")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(workflow), "governance-parity") {
		t.Fatal("canonical verification lacks the Go governance parity lane")
	}
}

package governance

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestTracingSchemaRootSymlink(t *testing.T) {
	for _, target := range []string{"inventory", "."} {
		t.Run(target, func(t *testing.T) {
			dir := t.TempDir()
			testWrite(t, dir, filepath.Join(target, "unowned.json"), []byte("{}"))
			if err := os.MkdirAll(filepath.Join(dir, "contracts"), 0o700); err != nil {
				t.Fatal(err)
			}
			if err := os.Symlink(filepath.Join("..", target), filepath.Join(dir, "contracts", "schemas")); err != nil {
				t.Fatal(err)
			}
			report, err := Check(t.Context(), Request{Tool: "contract-requirement-tracing", Root: dir})
			if err != nil {
				t.Fatal(err)
			}
			if len(report.Findings) != 1 || report.Findings[0].Path == nil || *report.Findings[0].Path != "contracts/schemas/unowned.json" {
				t.Fatalf("inventory=%v, want the untraced lexical schema path", report.Findings)
			}
		})
	}
}

func TestTracingUntrustedRequirementDirectory(t *testing.T) {
	dir := t.TempDir()
	outside := t.TempDir()
	if err := os.MkdirAll(filepath.Join(dir, "docs", "requirements"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(dir, "docs", "requirements", "GOV-001")); err != nil {
		t.Fatal(err)
	}
	report, err := Check(t.Context(), Request{Tool: "contract-requirement-tracing", Root: dir})
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Findings) != 1 || report.Findings[0].RuleID != "contract-requirement-record-unreadable" {
		t.Fatalf("unsafe authority inventory=%v", report.Findings)
	}
}

func TestTracingReportBypassesWaivers(t *testing.T) {
	dir := t.TempDir()
	testWrite(t, dir, "contracts/schemas/.json", []byte("{}"))
	testWrite(t, dir, exceptionPath, []byte("exceptions: [unclosed"))
	report, err := Check(t.Context(), Request{Tool: "contract-requirement-tracing", Root: dir, Mode: Inventory})
	if err != nil {
		t.Fatal(err)
	}
	if report.ExitCode != 0 || report.Text != "Published-contract requirement tracing report (issue #712)\n\n  - contracts/schemas/.json: UNTRACED\n" {
		t.Fatalf("report=%+v", report)
	}
	if removeErr := os.Remove(filepath.Join(dir, exceptionPath)); removeErr != nil {
		t.Fatal(removeErr)
	}
	report, err = Check(t.Context(), Request{Tool: "contract-requirement-tracing", Root: dir})
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Findings) != 1 || !strings.HasPrefix(report.Findings[0].Message, "published contract .json ") {
		t.Fatalf("dotfile contract identity=%v", report.Findings)
	}
}

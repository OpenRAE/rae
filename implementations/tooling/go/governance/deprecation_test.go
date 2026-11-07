package governance

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
)

func TestDeprecationUnreadableLedger(t *testing.T) {
	dir := t.TempDir()
	testWrite(t, dir, deprecationPath, []byte("policy: ecosystem-deprecation-records\n"))
	name := filepath.Join(dir, deprecationPath)
	if err := os.Chmod(name, 0); err != nil {
		t.Fatal(err)
	}
	if _, err := os.ReadFile(name); err == nil { // #nosec G304 -- name is a file in this test's private temporary directory.
		t.Skip("process can read files without permission bits")
	}
	_, err := Check(t.Context(), Request{Tool: "deprecation-lifecycle", Root: dir})
	if !errors.Is(err, fs.ErrPermission) {
		t.Fatalf("unreadable ledger became a policy verdict: %v", err)
	}
}

func TestDeprecationCurrentRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: "deprecation-lifecycle", Root: filepath.Join("..", "..", "..", "..")})
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Findings) != 0 || report.ExitCode != 0 {
		t.Fatalf("repository deprecation findings=%v, exit=%d", report.Findings, report.ExitCode)
	}
}

func TestDeprecationCatalogContainment(t *testing.T) {
	for _, outside := range []bool{false, true} {
		t.Run(map[bool]string{false: "inside", true: "outside"}[outside], func(t *testing.T) {
			checkDeprecationCatalogLink(t, outside)
		})
	}
}

func checkDeprecationCatalogLink(t *testing.T, outside bool) {
	t.Helper()
	dir := deltaFixture(t, "deprecation-reference", "schema-sharded")
	targetRoot := dir
	if outside {
		targetRoot = t.TempDir()
	}
	target := filepath.Join(targetRoot, "tombstone.json")
	testWrite(t, targetRoot, "tombstone.json", []byte(`{"schema_path":"contracts/schemas/old.json"}`))
	name := filepath.Join(dir, publicationTombstones, "old.json")
	if err := os.Remove(name); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, name); err != nil {
		t.Fatal(err)
	}
	report, err := Check(t.Context(), Request{Tool: "deprecation-lifecycle", Root: dir})
	if err != nil {
		t.Fatal(err)
	}
	if outside {
		if report.ExitCode != 1 || len(report.Findings) != 1 || report.Findings[0].RuleID != "deprecation-records-removal-tombstone" {
			t.Fatalf("outside tombstone accepted: %+v", report)
		}
	} else if report.ExitCode != 0 || len(report.Findings) != 0 {
		t.Fatalf("contained tombstone rejected: %+v", report)
	}
}

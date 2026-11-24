package governance

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
)

func TestPublicationDirectoryPermissions(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root bypasses ordinary directory permissions")
	}
	for _, directory := range []string{publicationEntries, publicationTombstones} {
		t.Run(filepath.Base(directory), func(t *testing.T) { checkPublicationDirectoryPermissions(t, directory) })
	}
}

func checkPublicationDirectoryPermissions(t *testing.T, directory string) {
	t.Helper()
	root := deltaFixture(t, "publication-reference", "sharded-valid")
	name := filepath.Join(root, directory)
	if err := os.Chmod(name, 0o100); err != nil { // #nosec G302 -- Search-only private fixture reproduces Path.glob suppression of enumeration errors.
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := os.Chmod(name, 0o700); err != nil { // #nosec G302 -- Restore owner-only access for temporary fixture cleanup.
			t.Error(err)
		}
	})
	report, err := Check(t.Context(), Request{Tool: schemaPublicationCheck, Root: root})
	if err != nil {
		t.Fatal(err)
	}
	want := 0
	if directory == publicationEntries {
		want = 1
	}
	if report.ExitCode != want {
		t.Fatalf("directory permissions report=%+v want exit=%d", report, want)
	}
}

func TestPublicationUnreadableRecord(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root bypasses ordinary file permissions")
	}
	root := deltaFixture(t, "publication-reference", "sharded-valid")
	name := filepath.Join(root, publicationEntries, "alpha-v1.json")
	if err := os.Chmod(name, 0); err != nil {
		t.Fatal(err)
	}
	_, err := Check(t.Context(), Request{Tool: schemaPublicationCheck, Root: root})
	if !errors.Is(err, fs.ErrPermission) {
		t.Fatalf("unreadable record became a policy verdict: %v", err)
	}
}

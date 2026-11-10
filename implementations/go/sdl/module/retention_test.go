package module

import (
	"bytes"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func TestPublicationRetainsCurrentPriorAndNewestVersions(t *testing.T) {
	output := t.TempDir()
	slot := filepath.Join(output, "module")
	versions := filepath.Join(slot, versionsDirectory)
	if err := os.MkdirAll(versions, 0700); err != nil {
		t.Fatal(err)
	}
	prior := "zz-prior"
	for index := range 13 {
		name := fmt.Sprintf("v%02d", index)
		if index == 0 {
			name = prior
		}
		directory := filepath.Join(versions, name)
		if err := os.Mkdir(directory, 0700); err != nil {
			t.Fatal(err)
		}
		mtime := time.Unix(int64(index), 0)
		if err := os.Chtimes(directory, mtime, mtime); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(slot, currentPointer), []byte(prior+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	current, err := publishLayout(t.Context(), output, "module", map[string][]byte{"index.json": []byte("{}\n")}, digest.SHA256([]byte("current")), defaultResourceLimits())
	if err != nil {
		t.Fatal(err)
	}
	entries, err := os.ReadDir(versions)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 8 {
		t.Fatalf("retained %d versions; want 8", len(entries))
	}
	for _, name := range []string{filepath.Base(current), prior, "v07", "v08", "v09", "v10", "v11", "v12"} {
		if _, err = os.Lstat(filepath.Join(versions, name)); err != nil {
			t.Errorf("retained reader/support version %q is missing: %v", name, err)
		}
	}
}

func TestVersionPruneFailurePreservesPointer(t *testing.T) {
	directory := t.TempDir()
	if err := os.MkdirAll(filepath.Join(directory, versionsDirectory, "new"), 0700); err != nil {
		t.Fatal(err)
	}
	prior := []byte("prior\n")
	if err := os.WriteFile(filepath.Join(directory, currentPointer), prior, 0600); err != nil {
		t.Fatal(err)
	}
	slot, err := os.OpenRoot(directory)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = slot.Close() }()
	versions, err := slot.OpenRoot(versionsDirectory)
	if err != nil {
		t.Fatal(err)
	}
	if err = versions.Close(); err != nil {
		t.Fatal(err)
	}
	if err = commitVersion(slot, versions, "new", "prior"); err == nil {
		t.Fatal("closed version store did not fail pruning")
	}
	pointer, err := fs.ReadFile(os.DirFS(directory), currentPointer)
	if err != nil || !bytes.Equal(pointer, prior) {
		t.Fatalf("failed pruning advanced the pointer: %q, %v", pointer, err)
	}
}

func TestRecoverySkipsUnrelatedVersionDirectories(t *testing.T) {
	output := t.TempDir()
	files := map[string][]byte{"index.json": []byte("{}\n")}
	identity := digest.SHA256([]byte("layout"))
	first, err := publishLayout(t.Context(), output, "module", files, identity, defaultResourceLimits())
	if err != nil {
		t.Fatal(err)
	}
	slot := filepath.Join(output, "module")
	if err = os.Remove(filepath.Join(slot, currentPointer)); err != nil {
		t.Fatal(err)
	}
	for index := range 80 {
		if err = os.Mkdir(filepath.Join(slot, versionsDirectory, fmt.Sprintf("a-unrelated-%03d", index)), 0700); err != nil {
			t.Fatal(err)
		}
	}
	recovered, err := publishLayout(t.Context(), output, "module", files, identity, defaultResourceLimits())
	if err != nil {
		t.Fatal(err)
	}
	if recovered != first {
		t.Fatal("valid matching orphan was hidden by unrelated versions")
	}
}

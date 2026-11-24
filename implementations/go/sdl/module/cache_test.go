package module

import (
	"bytes"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
)

func TestCacheRepairsCorruptionAndRecoversOrphans(t *testing.T) {
	fixture := readModuleReference(t)

	registry := referenceRegistry(t, fixture)
	first, err := registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact())
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(first.RootPath(), []byte("corrupt"), 0600); err != nil {
		t.Fatal(err)
	}
	second, err := registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact())
	if err != nil {
		t.Fatal(err)
	}
	actual, err := os.ReadFile(second.RootPath())
	if err != nil || !bytes.Equal(actual, fixture.Source) {
		t.Fatal("cache corruption was reused")
	}
	versionDirectory := filepath.Dir(second.RootPath())
	slot := filepath.Dir(filepath.Dir(versionDirectory))
	if err = os.Remove(filepath.Join(slot, ".raes-current")); err != nil {
		t.Fatal(err)
	}
	recovered, err := registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact())
	if err != nil {
		t.Fatal(err)
	}
	if recovered.RootPath() != second.RootPath() {
		t.Fatal("valid orphan version was not recovered")
	}
	if err = os.Remove(second.RootPath()); err != nil {
		t.Fatal(err)
	}
	outside := filepath.Join(t.TempDir(), "outside")
	if err = os.WriteFile(outside, []byte("preserve"), 0600); err != nil {
		t.Fatal(err)
	}
	if err = os.Symlink(outside, second.RootPath()); err != nil {
		t.Fatal(err)
	}
	repaired, err := registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact())
	if err != nil {
		t.Fatal(err)
	}
	if repaired.RootPath() == second.RootPath() {
		t.Fatal("symlinked immutable version reused")
	}
	actual, err = fs.ReadFile(os.DirFS(filepath.Dir(outside)), filepath.Base(outside))
	if err != nil || string(actual) != "preserve" {
		t.Fatal("cache repair followed a symlink")
	}
}

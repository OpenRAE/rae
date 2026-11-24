package module

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRegistryCacheRefusesFilesAndSymlinksBeforeOpeningStorage(t *testing.T) {
	directory := t.TempDir()
	file := filepath.Join(directory, "file")
	if err := os.WriteFile(file, []byte("preserve"), 0600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(directory, "link")
	if err := os.Symlink(directory, link); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"", file, filepath.Join(file, "child"), link} {
		registry, err := NewRegistry(name, DefaultPolicy(), nil)
		if err == nil || registry != nil {
			t.Fatalf("unsafe cache root accepted: %q", name)
		}
	}
	raw, err := os.ReadFile(file) //nolint:gosec // The path is a test-owned file under t.TempDir().
	if err != nil || string(raw) != "preserve" {
		t.Fatal("refused cache root was modified")
	}
}

func TestPublicationLayoutRefusesUnsafeAndLegacyStorage(t *testing.T) {
	directory := t.TempDir()
	file := filepath.Join(directory, "file")
	if err := os.WriteFile(file, []byte("preserve"), 0600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(directory, "link")
	if err := os.Symlink(directory, link); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"", filepath.Join(file, "child"), link} {
		if _, err := publishLayout(t.Context(), name, "module", nil, "identity", defaultResourceLimits()); err == nil {
			t.Fatalf("unsafe publication root accepted: %q", name)
		}
	}
	slot := filepath.Join(directory, "module")
	if err := os.Mkdir(slot, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(slot, "index.json"), []byte("legacy"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := publishLayout(t.Context(), directory, "module", nil, "identity", defaultResourceLimits()); err == nil {
		t.Fatal("legacy publication layout overwritten")
	}
	raw, err := os.ReadFile(filepath.Join(slot, "index.json")) //nolint:gosec // The path is a test-owned legacy fixture under t.TempDir().
	if err != nil || string(raw) != "legacy" {
		t.Fatal("refusal changed legacy publication bytes")
	}
}

package governance

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestRepositoryRootLink(t *testing.T) {
	target := t.TempDir()
	testWrite(t, target, "sample.txt", []byte("selected root"))
	link := filepath.Join(t.TempDir(), "root-link")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	r, err := openRepository(link)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	text, err := r.text("sample.txt")
	if err != nil || text != "selected root" || r.dir != r.absolute {
		t.Fatalf("linked repository text=%q error=%v directory=%q canonical=%q", text, err, r.dir, r.absolute)
	}
}

func TestRepositoryRootLinkParent(t *testing.T) {
	wrong, selected := t.TempDir(), t.TempDir()
	testWrite(t, wrong, "marker.txt", []byte("lexical parent"))
	testWrite(t, selected, "marker.txt", []byte("resolved parent"))
	if err := os.Mkdir(filepath.Join(selected, "deep"), 0o700); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(wrong, "link")
	if err := os.Symlink(filepath.Join(selected, "deep"), link); err != nil {
		t.Fatal(err)
	}
	// Concatenation deliberately retains the parent component until lookup.
	r, err := openRepository(link + string(filepath.Separator) + "..")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	text, err := r.text("marker.txt")
	if err != nil || text != "resolved parent" {
		t.Fatalf("selected the wrong repository: %q, %v", text, err)
	}
}

func TestRepositorySecretLinkParents(t *testing.T) {
	root := t.TempDir()
	link := filepath.Join(root, "root-link")
	// This target does not exist and is never inspected. Its link text alone
	// must refuse root selection before a filesystem traversal can follow it.
	if err := os.Symlink(filepath.Join(root, ".secrets"), link); err != nil {
		t.Fatal(err)
	}
	if _, err := openRepository(link); !errors.Is(err, errUnsafePath) {
		t.Fatalf("secret root link was not refused before traversal: %v", err)
	}
	testWrite(t, root, "tree/schema.json", []byte("permitted"))
	if err := os.Symlink(".secrets/../schema.json", filepath.Join(root, "tree/alias.json")); err != nil {
		t.Fatal(err)
	}
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	if _, err := r.read("tree/alias.json"); !errors.Is(err, errUnsafePath) {
		t.Fatalf("secret link text was normalized before its refusal: %v", err)
	}
	if _, err := r.read("tree/../tree/schema.json"); !errors.Is(err, errUnsafePath) {
		t.Fatalf("caller parent traversal became admissible: %v", err)
	}
}

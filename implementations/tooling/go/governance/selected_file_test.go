package governance

import (
	"errors"
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

func TestSelectedFileRefusesLateFinalSymlink(t *testing.T) {
	root := t.TempDir()
	testWrite(t, root, "selected", []byte("bound input"))
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	before, err := r.root.Lstat("selected")
	if err != nil {
		t.Fatal(err)
	}
	if renameErr := os.Rename(filepath.Join(root, "selected"), filepath.Join(root, "original")); renameErr != nil {
		t.Fatal(renameErr)
	}
	if linkErr := os.Symlink("original", filepath.Join(root, "selected")); linkErr != nil {
		t.Fatal(linkErr)
	}
	_, err = readSelectedFile(r, "selected", before, 1024)
	if !errors.Is(err, syscall.ELOOP) {
		t.Fatalf("late final link must be refused at open before reading its inode: %v", err)
	}
}

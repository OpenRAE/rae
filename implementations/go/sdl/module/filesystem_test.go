package module

import (
	"context"
	"os"
	"syscall"
	"testing"
)

func TestCanceledLockDoesNotCreateOrAcquireFile(t *testing.T) {
	root, err := os.OpenRoot(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = root.Close() })
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	handle, err := lockFile(ctx, root, "lock")
	if err == nil || handle != nil {
		t.Fatal("canceled lock was acquired")
	}
	if _, err = root.Lstat("lock"); !os.IsNotExist(err) {
		t.Fatalf("canceled operation created lock: %v", err)
	}
}

func TestReadRegularRejectsSpecialFilesAndSymlinks(t *testing.T) {
	name := t.TempDir()
	root, err := os.OpenRoot(name)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = root.Close() })
	if err = syscall.Mkfifo(name+"/fifo", 0600); err != nil {
		t.Fatal(err)
	}
	if err = root.Symlink("fifo", "link"); err != nil {
		t.Fatal(err)
	}
	for _, entry := range []string{"fifo", "link"} {
		if raw, _, err := readRegular(root, entry, 1024); err == nil || raw != nil {
			t.Fatalf("special file %s admitted", entry)
		}
	}
}

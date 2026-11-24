package module

import (
	"bytes"
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func TestCacheRejectsLinkedStoresAndLocks(t *testing.T) {
	fixture := readModuleReference(t)
	identity := strings.TrimPrefix(digest.SHA256(fixture.Artifact.Manifest), "sha256:")
	for _, location := range []string{".locks", ".locks/" + identity + ".lock", identity, identity + "/versions"} {
		t.Run(location, func(t *testing.T) { assertLinkedCacheRefused(t, fixture, location) })
	}
}
func assertLinkedCacheRefused(t *testing.T, fixture moduleReference, location string) {
	t.Helper()
	registry := referenceRegistry(t, fixture)
	outside := t.TempDir()
	target := filepath.Join(registry.directory, filepath.FromSlash(location))
	if err := os.MkdirAll(filepath.Dir(target), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, target); err != nil {
		t.Fatal(err)
	}
	if bundle, err := registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact()); err == nil || bundle != nil {
		t.Fatal("linked cache store acquired authority")
	}
	assertEmptyStore(t, outside)
}
func assertEmptyStore(t *testing.T, directory string) {
	t.Helper()
	entries, err := os.ReadDir(directory)
	if err != nil || len(entries) != 0 {
		t.Fatal("cache admission followed a linked store")
	}
}
func TestRegistryRejectsLinkedCacheRoot(t *testing.T) {
	directory, outside := t.TempDir(), t.TempDir()
	cache := filepath.Join(directory, "cache")
	if err := os.Symlink(outside, cache); err != nil {
		t.Fatal(err)
	}
	if registry, err := NewRegistry(cache, DefaultPolicy(), nil); err == nil {
		_ = registry.Close()
		t.Fatal("linked cache root admitted")
	}
	assertEmptyStore(t, outside)
}

func TestCacheRebuildsEveryInventoryMutation(t *testing.T) {
	fixture := readModuleReference(t)
	for _, kind := range []string{"content", "missing", "extra", "file-mode", "directory-mode", "metadata", "metadata-link", "metadata-fifo", "forged-tree"} {
		t.Run(kind, func(t *testing.T) {
			registry := referenceRegistry(t, fixture)
			first, err := registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact())
			if err != nil {
				t.Fatal(err)
			}
			version := filepath.Dir(first.RootPath())
			mutateCacheInventory(t, kind, first.RootPath(), version)
			rebuilt, err := registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact())
			if err != nil {
				t.Fatal(err)
			}
			if rebuilt.RootPath() == first.RootPath() {
				t.Fatal("invalid immutable version reused")
			}
			if !bytes.Equal(rebuilt.Sources()[fixture.Root], fixture.Source) || !bytes.Equal(first.Sources()[fixture.Root], fixture.Source) {
				t.Fatal("cache mutation changed captured source authority")
			}
		})
	}
}
func mutateCacheInventory(t *testing.T, kind, root, version string) {
	t.Helper()
	metadata := filepath.Join(version, cacheManifestName)
	var err error
	switch kind {
	case "content":
		err = os.WriteFile(root, []byte("changed"), 0600)
	case "missing":
		err = os.Remove(root)
	case "extra":
		err = os.WriteFile(filepath.Join(version, "extra"), nil, 0600)
	case "file-mode":
		err = os.Chmod(root, 0700) //nolint:gosec // Deliberately corrupt a cache file mode to verify rejection.
	case "directory-mode":
		err = os.Chmod(version, 0755) //nolint:gosec // Deliberately corrupt a cache directory mode to verify rejection.
	case "metadata":
		err = os.WriteFile(metadata, []byte("{}"), 0600)
	case "forged-tree":
		if err = os.WriteFile(root, []byte("changed"), 0600); err != nil {
			t.Fatal(err)
		}
		err = os.WriteFile(metadata, []byte(`{"entries":[],"tree_digest":"forged"}`), 0600)
	case "metadata-link", "metadata-fifo":
		if err = os.Remove(metadata); err != nil {
			t.Fatal(err)
		}
		if kind == "metadata-link" {
			err = os.Symlink(root, metadata)
		} else {
			err = syscall.Mkfifo(metadata, 0600)
		}
	}
	if err != nil {
		t.Fatal(err)
	}
}

func TestCacheConcurrentWritersReuseOneVersion(t *testing.T) {
	fixture := readModuleReference(t)
	registry := referenceRegistry(t, fixture)
	const workers = 8
	paths := make(chan string, workers)
	failures := make(chan error, workers)
	var group sync.WaitGroup
	for range workers {
		group.Go(func() {
			result, err := registry.Verify(t.Context(), "registry.example", fixture.Artifact.artifact())
			if err != nil {
				failures <- err
				return
			}
			paths <- result.RootPath()
		})
	}
	group.Wait()
	close(paths)
	close(failures)
	for err := range failures {
		t.Error(err)
	}
	first := ""
	for name := range paths {
		if first != "" && first != name {
			t.Fatal("concurrent writers published duplicate versions")
		}
		first = name
	}
	if first == "" {
		t.Fatal("no writer returned a verified module")
	}
	entries, err := fs.ReadDir(os.DirFS(filepath.Dir(filepath.Dir(first))), ".")
	if err != nil || len(entries) != 1 {
		t.Fatalf("immutable versions=%v, %v", entries, err)
	}
}

func TestLockWaitHonorsCancellationAndRejectsFIFO(t *testing.T) {
	directory := t.TempDir()
	root, err := os.OpenRoot(directory)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = root.Close() })
	held, err := lockFile(t.Context(), root, "lock")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = held.Close() })
	ctx, cancel := context.WithTimeout(t.Context(), 20*time.Millisecond)
	defer cancel()
	if second, lockErr := lockFile(ctx, root, "lock"); second != nil || !errors.Is(lockErr, context.DeadlineExceeded) {
		t.Fatalf("lock cancellation=%v, %v", second, lockErr)
	}
	if err = syscall.Mkfifo(filepath.Join(directory, "fifo"), 0600); err != nil {
		t.Fatal(err)
	}
	if special, err := lockFile(t.Context(), root, "fifo"); special != nil || err == nil {
		t.Fatal("FIFO lock admitted")
	}
}

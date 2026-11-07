package governance

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"testing"
)

func TestArtifactLocalAcquisition(t *testing.T) {
	data := []byte("reviewed snapshot")
	root := t.TempDir()
	testWrite(t, root, "snapshot", data)
	expected := lockedRawObject{size: json.Number(strconv.Itoa(len(data))), digest: fmt.Sprintf("%x", sha256.Sum256(data))}
	name := filepath.Join(root, "snapshot")
	// An invalid remote locator proves that an explicit local object never falls
	// through to the transport, either on success or refusal.
	got, err := acquireLockedBytes(t.Context(), "source", "invalid://unused", expected, name)
	if err != nil || string(got) != string(data) {
		t.Fatalf("local acquisition=%q, %v", got, err)
	}
	if err := os.Symlink("snapshot", name+".link"); err != nil {
		t.Fatal(err)
	}
	for _, selected := range []string{name + ".missing", name + ".link", root, filepath.Join(root, ".secrets", "never-created")} {
		_, err := acquireLockedBytes(t.Context(), "source", "invalid://unused", expected, selected)
		if typed, ok := errors.AsType[artifactAcquisitionError](err); !ok || string(typed) != "source local input failed locked identity validation" {
			t.Fatalf("explicit local refusal=%v", err)
		}
	}
	for _, size := range []json.Number{"0", "-1", "268435457", "1.0", "1e300", "99999999999999999999"} {
		wrong := expected
		wrong.size = size
		if _, err := acquireLockedBytes(t.Context(), "source", "invalid://unused", wrong, name); err == nil {
			t.Fatalf("admitted invalid locked size %s", size)
		}
	}
	for _, size := range []json.Number{"1", "18"} {
		wrong := expected
		wrong.size = size
		if _, err := acquireLockedBytes(t.Context(), "source", "invalid://unused", wrong, name); err == nil {
			t.Fatalf("admitted different exact size %s", size)
		}
	}
	expected.digest = "wrong"
	if _, err := acquireLockedBytes(t.Context(), "source", "invalid://unused", expected, name); err == nil {
		t.Fatal("admitted a different locked hash")
	}
}

func TestArtifactCurlReference(t *testing.T) {
	reference := readReference[struct {
		Versions []struct {
			Text      string
			Supported bool
		}
		Arguments []string
	}](t, "curl-reference")
	for _, version := range reference.Versions {
		if got := supportedCurlVersion(version.Text); got != version.Supported {
			t.Errorf("version %q=%v want %v", version.Text, got, version.Supported)
		}
	}
	args, err := artifactCurlArguments("https://example.invalid/source?x=1", "/private/raw", 123)
	if err != nil || !slices.Equal(args, reference.Arguments) {
		t.Fatalf("qualified argv=%q, %v want %q", args, err, reference.Arguments)
	}
	if !slices.Equal(artifactCurlEnvironment(), []string{"LC_ALL=C", "LANG=C", "PATH=/usr/bin:/bin"}) {
		t.Fatal("transport environment changed")
	}
	for _, locator := range []string{"http://example.invalid", "file:///tmp/raw", "https://user:pass@example.invalid", "https:///missing-host"} {
		if _, err := artifactCurlArguments(locator, "/private/raw", 123); err == nil {
			t.Fatalf("admitted locator %q", locator)
		}
	}
	for _, size := range []int64{0, -1, genericArtifactLimit + 1} {
		if _, err := artifactCurlArguments("https://example.invalid", "/private/raw", size); err == nil {
			t.Fatalf("admitted transfer size %d", size)
		}
	}
}

func TestArtifactCancellationCleanup(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	root := t.TempDir()
	testWrite(t, root, "partial", []byte("partial object"))
	output := filepath.Join(root, "partial")
	if _, err := runArtifactCurl(ctx, "https://example.invalid", output, 100); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation lost: %v", err)
	}
	if _, err := os.Lstat(output); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("failed transfer retained partial output: %v", err)
	}
	if _, err := acquireLockedBytes(ctx, "source", "https://example.invalid", lockedRawObject{}, ""); !errors.Is(err, context.Canceled) {
		t.Fatalf("acquisition cancellation lost: %v", err)
	}
}

func TestArtifactTemporaryDirectory(t *testing.T) {
	base := t.TempDir()
	t.Setenv("TMPDIR", base)
	dir, err := artifactTemporaryDirectory()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(dir) })
	info, err := os.Stat(dir)
	if err != nil || info.Mode().Perm() != 0o700 || filepath.Dir(dir) != base {
		t.Fatalf("private temporary directory: %v, %v", info, err)
	}
	t.Setenv("TMPDIR", filepath.Join(base, ".secrets", "never-created"))
	if _, err := artifactTemporaryDirectory(); err == nil {
		t.Fatal("admitted protected temporary directory")
	}
}

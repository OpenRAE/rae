package governance

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestRepositoryContainment(t *testing.T) {
	dir := t.TempDir()
	outside := t.TempDir()
	testWrite(t, dir, "file", []byte("inside"))
	testWrite(t, outside, "file", []byte("outside"))
	for name, target := range map[string]string{"relative": "file", "absolute": filepath.Join(dir, "file"), "escape": outside, "dangling": "absent", "missing-escape": filepath.Join(outside, "absent"), "loop": "loop"} {
		if err := os.Symlink(target, filepath.Join(dir, name)); err != nil {
			t.Fatal(err)
		}
	}
	r, err := openRepository(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = r.root.Close() })
	for _, name := range []string{"file", "relative", "absolute", "dangling", "absent/child", ""} {
		if !r.safe(name) {
			t.Errorf("safe(%q)=false, want contained", name)
		}
	}
	for _, name := range []string{"../file", outside, "escape/file", "missing-escape", "loop", ".secrets/key"} {
		if r.safe(name) {
			t.Errorf("safe(%q)=true, want refusal", name)
		}
	}
	for _, name := range []string{"file", "relative", "absolute"} {
		data, err := r.read(name)
		if err != nil || string(data) != "inside" {
			t.Errorf("read(%q)=%q,%v", name, data, err)
		}
	}
}

func TestChangedPathsPythonLineSeparators(t *testing.T) {
	dir := testGitRepository(t)
	testGit(t, dir, "config", "core.quotepath", "false")
	const name = "left\u2028right"
	testWrite(t, dir, name, []byte("before"))
	testCommit(t, dir)
	testWrite(t, dir, name, []byte("after"))
	r, err := openRepository(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = r.root.Close() })
	paths, err := r.changed(t.Context(), Request{})
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff([]string{"left", "right"}, paths); diff != "" {
		t.Fatal(diff)
	}
}

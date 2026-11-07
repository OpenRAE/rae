package governance

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRepositoryLinkParentReference(t *testing.T) {
	fixture := readReference[struct {
		Base  map[string]string
		Cases []repositoryLinkCase
	}](t, "link-parent-reference")
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) { checkRepositoryLinkCase(t, fixture.Base, tc) })
	}
}

type repositoryLinkCase struct {
	Name, Target, Text, Error string
	Links                     map[string]string
}

func checkRepositoryLinkCase(t *testing.T, base map[string]string, tc repositoryLinkCase) {
	t.Helper()

	root := seedRepositoryReference(t, repositoryReference{Files: base})
	for name, target := range tc.Links {
		if err := os.Symlink(strings.ReplaceAll(target, "%ROOT%", root), filepath.Join(root, name)); err != nil {
			t.Fatal(err)
		}
	}
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	target, err := r.resolve("tree/alias.json")
	if tc.Error != "" {
		if err == nil {
			t.Fatalf("reference %s became resolved target %q", tc.Error, target)
		}
		return
	}
	if err != nil || target != tc.Target {
		t.Fatalf("link target=%q error=%v want=%q", target, err, tc.Target)
	}
	text, err := r.text("tree/alias.json")
	if err != nil || text != tc.Text {
		t.Fatalf("link read=%q error=%v want=%q", text, err, tc.Text)
	}
}

func TestRepositoryLinkReentry(t *testing.T) {
	root := t.TempDir()
	testWrite(t, root, "selected.txt", []byte("selected"))
	for _, target := range []string{"../" + filepath.Base(root) + "/selected.txt", root + "/../" + filepath.Base(root) + "/selected.txt"} {
		link := filepath.Join(root, "alias")
		if err := os.Symlink(target, link); err != nil {
			t.Fatal(err)
		}
		r, err := openRepository(root)
		if err != nil {
			t.Fatal(err)
		}
		data, err := r.read("alias")
		_ = r.root.Close()
		if err != nil || string(data) != "selected" {
			t.Fatalf("target %q: %q %v", target, data, err)
		}
		if err := os.Remove(link); err != nil {
			t.Fatal(err)
		}
	}
}

func TestPRUserExpansion(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	for _, prefix := range []string{"~/", "./~/", ".//~//"} {
		got, err := prExpandUser(prefix + "linked/../event.json")
		if err != nil || got != os.Getenv("HOME")+"/linked/../event.json" {
			t.Fatalf("%q: %q %v", prefix, got, err)
		}
	}
	if _, err := prExpandUser("~no-such-raes-1799-test-account/event.json"); err == nil {
		t.Fatal("unknown account accepted")
	}
	t.Setenv("HOME", "")
	if got, err := prExpandUser("~/event.json"); err != nil || got != "/event.json" {
		t.Fatalf("empty HOME: %q %v", got, err)
	}
}

package governance

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type repoRegoReference struct {
	Name, Source, Input, Error string
	Findings                   []Finding
	NativeRefusal              bool
}

func TestRepoRegoReference(t *testing.T) {
	for _, tc := range readReference[[]repoRegoReference](t, "rego-reference") {
		t.Run(tc.Name, func(t *testing.T) { checkRepoRegoReference(t, tc) })
	}
}

func TestRepoRegoDirectorySafety(t *testing.T) {
	for _, mode := range []string{"contained-link", "directory-cycle", "unreadable-directory", "outside-link"} {
		t.Run(mode, func(t *testing.T) { checkRepoRegoDirectory(t, mode) })
	}
}

func checkRepoRegoReference(t *testing.T, tc repoRegoReference) {
	t.Helper()

	root := t.TempDir()
	testWrite(t, root, "tools/policy/conftest/rules.rego", []byte(tc.Source))
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	input, ok := referenceJSONValue(t, []byte(tc.Input)).(map[string]any)
	if !ok {
		t.Fatal("reference input must be an object")
	}
	findings, err := evaluateRepoRego(t.Context(), r, input)
	if tc.Error != "" || tc.NativeRefusal {
		if err == nil {
			t.Fatalf("refused policy became successful findings: %+v", findings)
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(tc.Findings, findings); diff != "" {
		t.Fatalf("Rego findings (-Conftest +native):\n%s", diff)
	}
}

func checkRepoRegoDirectory(t *testing.T, mode string) {
	t.Helper()

	if mode == "unreadable-directory" && os.Geteuid() == 0 {
		t.Skip("root bypasses permissions")
	}
	root := t.TempDir()
	testWrite(t, root, "tools/policy/conftest/base.rego", []byte("package main\nimport rego.v1\nhelper := true\n"))
	target := "private-rules"
	testWrite(t, root, target+"/deny.rego", []byte("package main\nimport rego.v1\ndeny contains \"linked denial\" if {true}\n"))
	target = prepareRepoRegoDirectory(t, root, mode, target)
	if mode != "unreadable-directory" {
		if !filepath.IsAbs(target) {
			target = filepath.Join(root, target)
		}
		if err := os.Symlink(target, filepath.Join(root, "tools/policy/conftest/linked")); err != nil {
			t.Fatal(err)
		}
	}
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	findings, err := evaluateRepoRego(t.Context(), r, map[string]any{})
	if mode == "contained-link" {
		if err != nil || len(findings) != 1 || findings[0].Message != "linked denial" {
			t.Fatalf("contained policy=%+v, %v", findings, err)
		}
	} else if err == nil {
		t.Fatalf("unsafe or unreadable policy was omitted: %+v", findings)
	}
}

func prepareRepoRegoDirectory(t *testing.T, root, mode, target string) string {
	t.Helper()
	switch mode {
	case "directory-cycle":
		target = "tools/policy/conftest"
	case "outside-link":
		target = t.TempDir()
	case "unreadable-directory":
		target = "tools/policy/conftest/unreadable"
		testWrite(t, root, target+"/deny.rego", []byte("package main\n"))
		selected := filepath.Join(root, target)
		if err := os.Chmod(selected, 0); err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() {
			// #nosec G302 -- Restore traversal permissions on the private test directory.
			if err := os.Chmod(selected, 0o700); err != nil {
				t.Error(err)
			}
		})
	}
	return target
}

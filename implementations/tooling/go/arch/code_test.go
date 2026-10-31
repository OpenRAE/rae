package arch

import (
	"context"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"
)

// validCode returns the code that matches validModel.
func validCode() Code {
	return Code{
		Modules: map[string]string{"m": "example.com/m"},
		Packages: map[string]Imports{
			"m/base/clock":  {},
			"m/base/hidden": {},
			"m/core/model":  {Code: []string{"m/base/clock"}},
			"m/core/inner":  {Code: []string{"m/core/model"}, Test: []string{"m/base/clock"}},
			"m/top/cli":     {Code: []string{"m/base/clock", "m/core/model"}, External: []string{"example.org/lib/sub"}},
		},
	}
}

type codeCase struct {
	name    string
	change  func(*Code)
	rule    string
	problem string
}

// codeCases returns one change of the code of validModel for each way in which
// code can break a rule, with the finding that the change causes.
func codeCases() []codeCase {
	return []codeCase{
		{"undeclared module", func(c *Code) { c.Modules["n"] = "example.com/n" }, "ARCH-001", "does not declare this Go module"},
		{"declared module without go.mod", func(c *Code) { delete(c.Modules, "m") }, "ARCH-001", "has no go.mod"},
		{"different module path", func(c *Code) { c.Modules["m"] = "example.com/x" }, "ARCH-001", `module path "example.com/x"`},
		{"undeclared package", func(c *Code) { c.Packages["m/base/extra"] = Imports{} }, "ARCH-005", "does not declare this package"},
		{"declared package without code", func(c *Code) { delete(c.Packages, "m/base/hidden") }, "ARCH-005", "has no code"},
		{
			"undeclared import",
			func(c *Code) { c.Packages["m/core/inner"] = Imports{Code: []string{"m/base/clock", "m/core/model"}} },
			"ARCH-006", "does not declare for this package",
		},
		{
			"unused declared import",
			func(c *Code) {
				c.Packages["m/top/cli"] = Imports{Code: []string{"m/core/model"}, External: []string{"example.org/lib"}}
			},
			"ARCH-006", "does not use",
		},
		{
			"test import from a layer that is not used",
			func(c *Code) {
				c.Packages["m/core/inner"] = Imports{Code: []string{"m/core/model"}, Test: []string{"m/top/cli"}}
			},
			"ARCH-007", "a test file: layer core may not use layer top",
		},
		{
			"unlisted external import",
			func(c *Code) {
				c.Packages["m/core/model"] = Imports{Code: []string{"m/base/clock"}, External: []string{"example.org/lib"}}
			},
			"ARCH-008", "does not list",
		},
		{
			"unused external entry",
			func(c *Code) { c.Packages["m/top/cli"] = Imports{Code: []string{"m/base/clock", "m/core/model"}} },
			"ARCH-008", "no package of the layer imports",
		},
	}
}

func TestCheckCodeAcceptsCodeThatMatchesTheModel(t *testing.T) {
	if findings := validModel().CheckCode(validCode()); len(findings) != 0 {
		t.Errorf("CheckCode() = %v, want no findings", findings)
	}
}

func TestCheckCodeReportsEachBrokenRule(t *testing.T) {
	for _, test := range codeCases() {
		t.Run(test.name, func(t *testing.T) {
			code := validCode()
			test.change(&code)
			if findings := validModel().CheckCode(code); !hasFinding(findings, test.rule, test.problem) {
				t.Errorf("CheckCode() = %v, want a %s finding about %q with a fix", findings, test.rule, test.problem)
			}
		})
	}
}

func TestDirOfSelectsTheLongestModulePath(t *testing.T) {
	model := &Model{Modules: []Module{
		{Dir: "a/b", Path: "example.com/a/b"},
		{Dir: "a", Path: "example.com/a"},
		{Dir: "c", Path: "example.com/a/b/c/d"},
	}}
	tests := map[string]string{
		"example.com/a":         "a",
		"example.com/a/x":       "a/x",
		"example.com/a/b/x":     "a/b/x",
		"example.com/a/b/c/d/e": "c/e",
		"example.com/ab":        "",
		"fmt":                   "",
	}
	for importPath, want := range tests {
		got, ok := model.dirOf(importPath)
		if got != want || ok != (want != "") {
			t.Errorf("dirOf(%q) = %q, %t, want %q, %t", importPath, got, ok, want, want != "")
		}
	}
}

func TestFindModulesSkipsTheDirectoriesThatTheGoCommandIgnores(t *testing.T) {
	module := func(path string) *fstest.MapFile { return &fstest.MapFile{Data: []byte("module " + path + "\n")} }
	fsys := fstest.MapFS{
		"a/go.mod":          module("example.com/a"),
		"a/b/go.mod":        module(`"example.com/a/b" // A quoted path.`),
		"a/testdata/go.mod": module("example.com/t"),
		"a/.hidden/go.mod":  module("example.com/h"),
		"a/_skip/go.mod":    module("example.com/s"),
		"c/go.sum":          {},
	}
	got, err := findModules(fsys)
	if err != nil {
		t.Fatalf("findModules() error = %v", err)
	}
	want := map[string]string{"a": "example.com/a", "a/b": "example.com/a/b"}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("findModules() mismatch (-want +got):\n%s", diff)
	}
}

func TestFindModulesReportsAnUnreadableGoMod(t *testing.T) {
	if _, err := findModules(fstest.MapFS{"a/go.mod": {Mode: fs.ModeSymlink}}); err == nil {
		t.Error("findModules() error = nil, want an error")
	}
}

func TestLoadCodeRecordsTheImportsOfEachPackageAndItsTests(t *testing.T) {
	root := writeTree(t, map[string]string{
		"ext/go.mod":    "module example.org/ext\n\ngo 1.27\n",
		"ext/x/x.go":    "package x\n",
		"m/go.mod":      "module example.com/m\n\ngo 1.27\n\nrequire example.org/ext v0.0.0\n\nreplace example.org/ext => ../ext\n",
		"m/a/a.go":      "package a\n\nimport (\n\t_ \"fmt\"\n\n\t_ \"example.com/m/b\"\n\t_ \"example.org/ext/x\"\n)\n",
		"m/a/a_test.go": "package a\n\nimport _ \"example.com/m/c\"\n",
		"m/a/x_test.go": "package a_test\n\nimport (\n\t_ \"example.com/m/a\"\n\t_ \"example.com/m/d\"\n)\n",
		"m/b/b.go":      "package b\n",
		"m/c/c.go":      "package c\n",
		"m/d/d.go":      "package d\n\nimport _ \"example.com/m/a\"\n",
		"w/go.mod":      "module example.com/other\n\ngo 1.27\n",
		"w/p/p.go":      "package p\n\nimport (\n",
	})
	model := &Model{Modules: []Module{
		{Dir: "m", Path: "example.com/m"},
		{Dir: "gone", Path: "example.com/gone"},
		{Dir: "w", Path: "example.com/w"},
	}}
	got, err := LoadCode(t.Context(), root, model)
	if err != nil {
		t.Fatalf("LoadCode() error = %v", err)
	}
	want := Code{
		Modules: map[string]string{"ext": "example.org/ext", "m": "example.com/m", "w": "example.com/other"},
		Packages: map[string]Imports{
			"m/a": {Code: []string{"m/b"}, Test: []string{"m/c", "m/d"}, External: []string{"example.org/ext/x"}},
			"m/b": {},
			"m/c": {},
			"m/d": {Code: []string{"m/a"}},
		},
	}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("LoadCode() mismatch (-want +got):\n%s", diff)
	}
}

func TestLoadCodeReportsAFailure(t *testing.T) {
	model := &Model{Modules: []Module{{Dir: "m", Path: "example.com/m"}}}
	tests := map[string]struct {
		files    map[string]string
		canceled bool
	}{
		"missing repository": {files: nil},
		"canceled load": {
			files:    map[string]string{"m/go.mod": "module example.com/m\n\ngo 1.27\n", "m/p/p.go": "package p\n"},
			canceled: true,
		},
		"package error": {files: map[string]string{
			"m/go.mod": "module example.com/m\n\ngo 1.27\n",
			"m/p/p.go": "package p\n\nimport (\n",
		}},
	}
	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			root := filepath.Join(t.TempDir(), "missing")
			if test.files != nil {
				root = writeTree(t, test.files)
			}
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()
			if test.canceled {
				cancel()
			}
			if _, err := LoadCode(ctx, root, model); err == nil {
				t.Error("LoadCode() error = nil, want an error")
			}
		})
	}
}

// writeTree writes files, keyed by slash-separated path, under a new
// temporary directory and returns the directory.
func writeTree(t *testing.T, files map[string]string) string {
	t.Helper()
	root := t.TempDir()
	for name, content := range files {
		file := filepath.Join(root, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(file), 0o750); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(file, []byte(content), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

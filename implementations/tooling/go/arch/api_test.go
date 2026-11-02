package arch

import (
	"errors"
	"go/ast"
	"go/parser"
	"go/token"
	"go/types"
	"io/fs"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

func typedFixture(t *testing.T, src string) *types.Package {
	t.Helper()
	return typedNamedFixture(t, "p", src)
}

func typedNamedFixture(t *testing.T, name, src string) *types.Package {
	t.Helper()
	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, "p.go", "package "+name+"\n"+src, 0)
	if err != nil {
		t.Fatal(err)
	}
	pkg, err := new(types.Config).Check("example.com/p", fset, []*ast.File{file}, nil)
	if err != nil {
		t.Fatal(err)
	}
	return pkg
}

func TestTypedAPIChangesAndPrivateStability(t *testing.T) {
	base := "type hidden struct { Value string }; type Public struct { hidden; Name string `json:\"name\"` }; const Limit = 42; var Default = 1; func New() hidden { return hidden{} }; func (*Public) Run(v int) error { return nil }; func private() {}"
	want := typeAPI(typedFixture(t, base))
	for _, change := range []struct{ old, new string }{
		{"Value string", "Value int"}, {"Name string", "Name []byte"}, {"json:\"name\"", "json:\"other\""}, {"= 42", "= 43"}, {"Default = 1", "Default = 1.5"}, {"v int", "v string"}, {"(*Public)", "(Public)"},
	} {
		src := strings.Replace(base, change.old, change.new, 1)
		if got := typeAPI(typedFixture(t, src)); slices.Equal(got, want) {
			t.Errorf("API unchanged for %s", change.new)
		}
	}
	if got := typeAPI(typedFixture(t, base+"\nfunc other() int { return 3 }")); !slices.Equal(got, want) {
		t.Errorf("private change changed API: %v", got)
	}
}

func TestLoadAPICoversBuildTagsAndRejectsUndesignedExports(t *testing.T) {
	root := writeTree(t, map[string]string{
		"m/go.mod":            "module example.com/m\n\ngo 1.27\n",
		"m/base/clock/a.go":   "package clock\nfunc Exported() int { return 1 }\n",
		"m/base/clock/tag.go": "//go:build extra\n\npackage clock\nconst Tagged=3\n",
	})
	m := &Model{Modules: []Module{{Dir: "m", Path: "example.com/m"}}, Packages: []Package{{Dir: "m/base/clock", API: map[string][]string{"linux": {}}}}, Configurations: []Configuration{{ID: "linux", GOOS: "linux", GOARCH: "amd64"}}}
	if _, err := LoadAPI(t.Context(), root, m); err == nil {
		t.Fatal("LoadAPI() accepted uncovered tagged source")
	}
	m.Configurations = append(m.Configurations, Configuration{ID: "extra", GOOS: "linux", GOARCH: "amd64", Tags: []string{"extra"}})
	actual, err := LoadAPI(t.Context(), root, m)
	if err != nil {
		t.Fatal(err)
	}
	if got := m.CheckAPI(actual); !hasFinding(got, ruleAPI, "exported API differs") {
		t.Fatalf("CheckAPI() = %v, want undesigned-export finding", got)
	}
	if slices.Equal(actual["m/base/clock"]["linux"], actual["m/base/clock"]["extra"]) {
		t.Fatal("LoadAPI() lost the tagged export")
	}
	m.Packages[0].API = actual["m/base/clock"]
	if got := m.CheckAPI(actual); len(got) != 0 {
		t.Errorf("CheckAPI() = %v, want no findings", got)
	}
}

func TestTypedAPIDetectsPositionalLiteralRestriction(t *testing.T) {
	before := typeAPI(typedFixture(t, "type Public struct { Value string }"))
	after := typeAPI(typedFixture(t, "type Public struct { Value string; hidden int }"))
	if slices.Equal(before, after) {
		t.Fatal("typeAPI() lost the private-field restriction on consumer positional literals")
	}
	stable := typeAPI(typedFixture(t, "type Public struct { Value string; renamed string }"))
	if !slices.Equal(after, stable) {
		t.Fatal("typeAPI() changed for an inaccessible field with the same public properties")
	}
}

func TestTypedAPITracksReachableGenericAndContainerTypes(t *testing.T) {
	source := `type Number interface { ~int | ~int64 }
 type hidden struct { Value string }
 type Box[T Number] struct { Value T }
 type Alias = hidden
 type Service interface { Run(*hidden) ([]hidden, error) }
 func Transform[T Number](x map[string]chan<- [2][]*Box[T]) func(T) T { return nil }
 var Value struct { Item *hidden }
 `
	original := typeAPI(typedFixture(t, source))
	for _, change := range []struct{ from, to string }{{"Value string", "Value bool"}, {"~int64", "~int32"}, {"[2]", "[3]"}, {"chan<-", "<-chan"}, {"type Alias = hidden", "type Alias = Service"}} {
		if altered := typeAPI(typedFixture(t, strings.Replace(source, change.from, change.to, 1))); slices.Equal(original, altered) {
			t.Errorf("typeAPI() lost change %s", change.to)
		}
	}
}

func TestAPITracksDependencyOwnedAliasesAndEmbeddedFields(t *testing.T) {
	root := writeTree(t, map[string]string{
		"m/go.mod":           "module example.com/m\n\ngo 1.27\n",
		"m/dep/dep.go":       "package dep\ntype Value struct { Field string };func (*Value) Method() int {return 1}\n",
		"m/client/client.go": "package client\nimport \"example.com/m/dep\"\ntype Alias = dep.Value;type Embedded struct {dep.Value}\n",
	})
	model := &Model{Modules: []Module{{Dir: "m", Path: "example.com/m"}}, Configurations: []Configuration{{ID: "linux", GOOS: "linux", GOARCH: "amd64"}}, Packages: []Package{{Dir: "m/dep"}, {Dir: "m/client"}}}
	initial, err := LoadAPI(t.Context(), root, model)
	if err != nil {
		t.Fatal(err)
	}
	for _, replacement := range []string{"type Value struct {Field int};func (*Value) Method() int {return 1}", "type Value struct {Field string};func (*Value) Method() string {return \"value\"}"} {
		if err := os.WriteFile(filepath.Join(root, "m/dep/dep.go"), []byte("package dep\n"+replacement), 0600); err != nil {
			t.Fatal(err)
		}
		actual, err := LoadAPI(t.Context(), root, model)
		if err != nil {
			t.Fatal(err)
		}
		// Updating the dependency contract alone cannot bless the client's exposed API.
		model.Packages[0].API = actual["m/dep"]
		model.Packages[1].API = initial["m/client"]
		if findings := model.CheckAPI(actual); !hasFinding(findings, ruleAPI, "exported API differs") {
			t.Fatal("CheckAPI() accepted dependency API drift through client aliases and embeds")
		}
	}
}

func TestTypedAPITracksDeclaredPackageName(t *testing.T) {
	before := typeAPI(typedNamedFixture(t, "p", "func F() {}"))
	after := typeAPI(typedNamedFixture(t, "q", "func F() {}"))
	if slices.Equal(before, after) {
		t.Fatal("typeAPI() accepted a package rename at an unchanged import path and exported surface")
	}
}

func TestAPICoverageRejectsEscapingPackageDirectory(t *testing.T) {
	root := writeTree(t, map[string]string{"m/go.mod": "module example.com/m\n\ngo 1.27\n"})
	outside := writeTree(t, map[string]string{"private-location.go": "private data"})
	if err := os.Symlink(outside, filepath.Join(root, "m/escaped")); err != nil {
		t.Fatal(err)
	}
	err := checkAPICoverage(root, &Model{Packages: []Package{{Dir: "m/escaped"}}}, map[string]bool{})
	if err == nil || strings.Contains(err.Error(), "private-location.go") {
		t.Fatalf("coverage error = %v, want containment refusal without outside directory entries", err)
	}
}

func TestAPISourceContainmentAndIgnoredDirectories(t *testing.T) {
	root := writeTree(t, map[string]string{"m/go.mod": "module example.com/m\n\ngo 1.27\n", "m/p/p.go": "package p\n"})
	outside := filepath.Join(t.TempDir(), "outside.go")
	if err := os.WriteFile(outside, []byte("private"), 0600); err != nil {
		t.Fatal(err)
	}
	model := &Model{Modules: []Module{{Dir: "m", Path: "example.com/m"}}}
	if err := validateAPITree(filepath.Join(root, "missing"), model); err == nil {
		t.Fatal("validateAPITree() accepted a missing root")
	}
	if err := os.Mkdir(filepath.Join(root, "m/.ignored"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(root, "m/.ignored/hidden.go")); err != nil {
		t.Fatal(err)
	}
	if err := validateAPITree(root, model); err != nil {
		t.Fatalf("ignored Go directory blocked validation: %v", err)
	}
	if err := os.Remove(filepath.Join(root, "m/go.mod")); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"m/p/escape.go", "m/go.mod"} {
		if err := os.Symlink(outside, filepath.Join(root, name)); err != nil {
			t.Fatal(err)
		}
		err := validateAPITree(root, model)
		var pathError *fs.PathError
		if !errors.As(err, &pathError) || pathError.Path != name {
			t.Errorf("validateAPITree(%s) error = %v, want the original rooted file error", name, err)
		}
		if err := os.Remove(filepath.Join(root, name)); err != nil {
			t.Fatal(err)
		}
	}
}

package arch

import (
	"go/importer"
	"go/types"
	"slices"
	"strings"
	"testing"
	"testing/fstest"

	"golang.org/x/tools/go/packages"
)

func TestConsumerStandardPackagesPreserveDependencies(t *testing.T) {
	clock := types.NewPackage("time", "time")
	root := &packages.Package{PkgPath: "example.com/m", Types: types.NewPackage("example.com/m", "m"), Imports: map[string]*packages.Package{"time": {PkgPath: "time", Types: clock}}}
	got, err := consumerStandardPackages([]*packages.Package{root})
	if err != nil || len(got) != 1 || got["time"] != clock {
		t.Fatalf("shared dependencies = %v, %v", got, err)
	}
	root.Imports["time"].Errors = []packages.Error{{Msg: "invalid dependency"}}
	if _, err = consumerStandardPackages([]*packages.Package{root}); err == nil {
		t.Error("dependency load error was ignored")
	}
}

func TestConsumerStandardImportsReuseBoundedDeclarations(t *testing.T) {
	m, repo := typedConsumerFixture("package example; import \"io\"; type Value interface { Writer() io.Writer }")
	c := newConsumerTypes(m, repo)
	standard, err := c.standardImports()
	if err != nil || !slices.Equal(standard, []string{"io"}) {
		t.Fatalf("standard imports = %v, %v", standard, err)
	}
	remaining := c.remaining
	if err = c.checkPackages(); err != nil {
		t.Fatal(err)
	}
	if c.remaining != remaining {
		t.Fatal("type checking re-read declarations outside the shared budget")
	}
}

func TestConsumerStandardImportsPreservePackageValidation(t *testing.T) {
	for _, tc := range []string{"undeclared dependency", "missing file", "reused source"} {
		t.Run(tc, func(t *testing.T) {
			m, repo := typedConsumerFixture("package example; type Value struct{}")
			switch tc {
			case "undeclared dependency":
				m, repo = typedConsumerFixture("package example; import \"example.com/m/dep\"; type Value dep.Value")
				m.ConsumerAPI.Packages = append(m.ConsumerAPI.Packages, ConsumerPackage{Owner: "rae", Path: "dep"})
			case "missing file":
				delete(repo, m.ConsumerAPI.Packages[0].Declarations)
			case "reused source":
				other := m.ConsumerAPI.Packages[0]
				other.Path = "other"
				m.ConsumerAPI.Packages = append(m.ConsumerAPI.Packages, other)
			}
			if _, err := newConsumerTypes(m, repo).standardImports(); err == nil {
				t.Error("invalid declaration was accepted during import discovery")
			}
		})
	}
}

func typedConsumerFixture(source string) (*Model, fstest.MapFS) {
	name := "implementations/architecture-api/planned/rae/example.go.txt"
	m := validModel()
	m.ConsumerAPI = &ConsumerAPI{Modules: []ConsumerModule{{Owner: "rae", Module: "example.com/m"}}, Packages: []ConsumerPackage{{Owner: "rae", Path: "example", Symbols: []string{"Value"}, Declarations: name, DeclarationsSHA256: contentDigest([]byte(source))}}}
	return m, fstest.MapFS{name: &fstest.MapFile{Data: []byte(source)}}
}

func TestConsumerTypesRejectInvalidContracts(t *testing.T) {
	for _, tc := range []struct{ name, source string }{
		{"undefined field", "package example; type Value struct { Field Missing }"},
		{"undefined selector", "package example; import \"io\"; type Value struct { Field io.DoesNotExist }"},
		{"missing export", "package example; type Other struct {}"},
		{"foreign dependency", "package example; import \"example.com/foreign\"; type Value struct { Field foreign.Value }"},
		{"malformed declaration", "package example; type Value struct {"},
		{"wrong package", "package other; type Value struct {}"},
		{"variable initializer", "package example; type Value struct{}; var F = func() {}"},
		{"implementation body", "package example; type Value struct {}; func Run() {}"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			m, repo := typedConsumerFixture(tc.source)
			if err := newConsumerTypes(m, repo).checkPackages(); err == nil {
				t.Error("invalid public Go contract was accepted")
			}
		})
	}
}

func TestConsumerTypesBindSourceAndBounds(t *testing.T) {
	for _, tc := range []string{"stale source", "unsafe path", "missing file", "oversized source", "read budget"} {
		t.Run(tc, func(t *testing.T) {
			m, repo := typedConsumerFixture("package example; type Value struct {}")
			p := &m.ConsumerAPI.Packages[0]
			switch tc {
			case "stale source":
				repo[p.Declarations].Data = []byte("package example; type Value struct { Changed string }")
			case "unsafe path":
				p.Declarations = "../example.go.txt"
			case "missing file":
				delete(repo, p.Declarations)
			case "oversized source":
				repo[p.Declarations].Data = []byte(strings.Repeat(" ", 65537))
			case "read budget":
				remaining := 0
				if _, _, err := readConsumerDeclaration(repo, *p, &remaining); err == nil {
					t.Error("exhausted consumer read budget was accepted")
				}
				return
			}
			if err := newConsumerTypes(m, repo).checkPackages(); err == nil {
				t.Error("unsafe or stale public declaration was accepted")
			}
		})
	}
}

func TestConsumerTypesResolveMethodsAndSharedTypes(t *testing.T) {
	m, repo := typedConsumerFixture("package example; import \"io\"; type Value interface { Read([]byte)(int,error); Writer()io.Writer }")
	m.ConsumerAPI.Packages[0].Symbols = []string{"Value", "Value.Read", "Value.Writer"}
	if err := newConsumerTypes(m, repo).checkPackages(); err != nil {
		t.Fatal(err)
	}
	m.ConsumerAPI.Packages[0].Symbols = []string{"Value.Absent"}
	if err := newConsumerTypes(m, repo).checkPackages(); err == nil {
		t.Error("invented method was accepted")
	}
}

func TestConsumerTypesRequireDeclaredImportClosure(t *testing.T) {
	m, repo := typedConsumerFixture("package example; import \"example.com/m/dep\"; type Value struct{ Field dep.Value }")
	name := "implementations/architecture-api/planned/rae/dep.go.txt"
	source := "package dep; type Value struct{}"
	repo[name] = &fstest.MapFile{Data: []byte(source)}
	m.ConsumerAPI.Packages = append(m.ConsumerAPI.Packages, ConsumerPackage{Owner: "rae", Path: "dep", Symbols: []string{"Value"}, Declarations: name, DeclarationsSHA256: contentDigest([]byte(source))})
	if err := newConsumerTypes(m, repo).checkPackages(); err == nil || !strings.Contains(err.Error(), "absent from uses") {
		t.Errorf("undeclared import check = %v", err)
	}
	m.ConsumerAPI.Packages[0].Uses = []string{"rae:dep"}
	if err := newConsumerTypes(m, repo).checkPackages(); err != nil {
		t.Fatal(err)
	}
}

func TestConsumerTypesRejectDivergentImplementedAPI(t *testing.T) {
	m, repo := typedConsumerFixture("package example; type Value struct { Data int }")
	c := &consumerTypes{model: m, repo: repo, checked: map[string]*types.Package{}, loading: map[string]bool{}, standard: importer.Default(), remaining: 4 * 1024 * 1024}
	compiled, err := c.Import("example.com/m/example")
	if err != nil {
		t.Fatal(err)
	}
	m.Packages = append(m.Packages, Package{Dir: "m/example", API: map[string][]string{"linux": typeAPI(compiled)}})
	if err = newConsumerTypes(m, repo).checkPackages(); err != nil {
		t.Fatal(err)
	}
	p := &m.ConsumerAPI.Packages[0]
	repo[p.Declarations].Data = []byte("package example; type Value struct { Data string }")
	p.DeclarationsSHA256 = contentDigest(repo[p.Declarations].Data)
	if err = newConsumerTypes(m, repo).checkPackages(); err == nil || !strings.Contains(err.Error(), "typed consumer contract") {
		t.Errorf("changed field contract check = %v", err)
	}
}

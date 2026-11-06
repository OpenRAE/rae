package arch

import (
	"encoding/json"
	"os"
	"slices"
	"strings"
	"testing"
)

func consumerModel(t *testing.T) *Model {
	t.Helper()
	m, err := Load(os.DirFS(extractionRoot(t)), "implementations/architecture.json")
	if err != nil {
		t.Fatal(err)
	}
	if m.ConsumerAPI == nil {
		t.Fatal("the repository needs a public consumer API design")
	}
	return m
}

func consumerPackage(t *testing.T, m *Model, id string) *ConsumerPackage {
	t.Helper()
	for i := range m.ConsumerAPI.Packages {
		p := &m.ConsumerAPI.Packages[i]
		if p.Owner+":"+p.Path == id {
			return p
		}
	}
	t.Fatalf("missing public package %s", id)
	return nil
}

func TestConsumerAPIDesign(t *testing.T) {
	m := consumerModel(t)
	if got := m.CheckDesign(); len(got) != 0 {
		t.Fatalf("CheckDesign() = %v", got)
	}
	for _, change := range []func(*ConsumerAPI){
		func(a *ConsumerAPI) { a.Packages = append(a.Packages, a.Packages[0]) },
		func(a *ConsumerAPI) { a.Packages[0].Owner = "third-contracts-repo" },
		func(a *ConsumerAPI) { a.Packages[0].Layer = "missing" },
		func(a *ConsumerAPI) { a.Packages[0].Symbols = []string{"private"} },
		func(a *ConsumerAPI) { a.Design = "../design.md" },
		func(a *ConsumerAPI) { a.Modules = append(a.Modules, a.Modules[0]) },
		func(a *ConsumerAPI) { a.Modules = nil },
		func(a *ConsumerAPI) { a.Modules[1].Owner = "other" },
		func(a *ConsumerAPI) { a.Modules[1].Module = "github.com/OpenRAE/example" },
		func(a *ConsumerAPI) { a.Modules[1].Repository = "OpenRAE/example" },
		func(a *ConsumerAPI) {
			a.Modules[1].Repository = "OpenRAE/example"
			a.Modules[1].Module = "github.com/OpenRAE/example-impersonator"
		},
		func(a *ConsumerAPI) {
			a.Modules[1].Repository = "OpenRAE/rae"
			a.Modules[1].Module = "github.com/OpenRAE/rae/implementations/go"
		},
		func(a *ConsumerAPI) { a.Design = "docs/absent.md" },
		func(a *ConsumerAPI) { a.Packages[0].Symbols = nil },
		func(a *ConsumerAPI) { a.Packages[0].Symbols = []string{"A.B.C"} },
		func(a *ConsumerAPI) { a.Packages[0].Symbols = []string{"Error", "Error"} },
		func(a *ConsumerAPI) { a.Packages[0].Issues = nil },
		func(a *ConsumerAPI) { a.Packages[0].Issues = []int{0} },
		func(a *ConsumerAPI) { a.Packages[0].Consumers = nil },
		func(a *ConsumerAPI) { a.Packages[0].Layer = "runtime" },
		func(a *ConsumerAPI) { a.Packages[0].Issues = []int{1780} },
	} {
		m = consumerModel(t)
		change(m.ConsumerAPI)
		if !hasFinding(m.CheckDesign(), "ARCH-015", "consumer") {
			t.Error("invalid consumer design was accepted")
		}
	}
}

func TestConsumerAPIConsumers(t *testing.T) {
	m := consumerModel(t)
	for _, consumer := range []string{"environment-packs", "lilrae", "coldlight", "runtime"} {
		if !slices.ContainsFunc(m.ConsumerAPI.Packages, func(p ConsumerPackage) bool { return slices.Contains(p.Consumers, consumer) }) {
			t.Errorf("no public operations for %s", consumer)
		}
	}
	consumerPackage(t, m, "rae:sdl").Consumers = []string{"unknown-consumer"}
	if !hasFinding(m.CheckDesign(), "ARCH-015", "consumer") {
		t.Error("unknown consumer was accepted")
	}
}

func TestConsumerAPIBoundaries(t *testing.T) {
	for _, tc := range []struct {
		name   string
		change func(*Model)
	}{
		{"internal", func(m *Model) { consumerPackage(t, m, "rae:sdl").Path = "internal/sdl" }},
		{"main package", func(m *Model) { consumerPackage(t, m, "rae:sdl").Path = "cmd/sdl" }},
		{"invalid segment", func(m *Model) { consumerPackage(t, m, "rae:sdl").Path = "sdl/invalid-path" }},
		{"layer direction", func(m *Model) { consumerPackage(t, m, "rae:base/clock").Uses = []string{"rae:sdl"} }},
		{"escape", func(m *Model) { consumerPackage(t, m, "rae:sdl").Path = "../sdl" }},
		{"reverse permitted layer", func(m *Model) { consumerPackage(t, m, "rae:conformance").Uses = []string{"runtime:runtime/control"} }},
		{"reverse", func(m *Model) { consumerPackage(t, m, "rae:sdl").Uses = []string{"runtime:runtime/control"} }},
		{"missing import", func(m *Model) { consumerPackage(t, m, "rae:sdl").Uses = []string{"rae:missing"} }},
		{"self import", func(m *Model) { consumerPackage(t, m, "rae:sdl").Uses = []string{"rae:sdl"} }},
		{"same layer cycle", func(m *Model) {
			p := consumerPackage(t, m, "rae:processor")
			p.Uses = append(p.Uses, "rae:processor/planning")
		}},
		{"cycle", func(m *Model) { consumerPackage(t, m, "rae:contract/admission").Uses = []string{"rae:sdl"} }},
		{"reverse command", func(m *Model) { m.ConsumerAPI.Commands[1].Uses = []string{"runtime:runtime/control"} }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			m := consumerModel(t)
			tc.change(m)
			problem := "consumer"
			if slices.Contains([]string{"internal", "main package", "escape", "invalid segment"}, tc.name) {
				problem = "public Go path"
			}
			if tc.name == "same layer cycle" {
				problem = "consumer dependency cycle"
			}
			if !hasFinding(m.CheckDesign(), "ARCH-015", problem) {
				t.Error("unsafe consumer dependency was accepted")
			}
		})
	}
}

func TestConsumerAPIDelivery(t *testing.T) {
	m := consumerModel(t)
	for _, p := range m.ConsumerAPI.Packages {
		if len(p.Issues) == 0 || len(p.Symbols) == 0 {
			t.Errorf("%s:%s lacks a concrete delivery commitment", p.Owner, p.Path)
		}
		if p.Existing != "" {
			if _, ok := m.pkg(p.Existing); !ok || !slices.Contains(p.Issues, 1892) {
				t.Errorf("invalid relocation commitment: %+v", p)
			}
		}
	}
	m.ConsumerAPI.Packages[0].Existing = "missing/source"
	if !hasFinding(m.CheckDesign(), "ARCH-015", "consumer") {
		t.Error("nonexistent relocation source was accepted")
	}
}

func TestConsumerAPICompatibility(t *testing.T) {
	m := consumerModel(t)
	if len(m.ConsumerAPI.Commands) != 2 || m.ConsumerAPI.Commands[0].Name != "raes" || m.ConsumerAPI.Commands[0].Owner != "runtime" || m.ConsumerAPI.Commands[1].Name != "raes-mcp" || m.ConsumerAPI.Commands[1].Owner != "rae" {
		t.Fatal("each existing executable needs its decided publisher")
	}
	// Only the relocated packages are implemented; the other plans have no code.
	for _, p := range m.ConsumerAPI.Packages {
		if _, implemented := m.pkg("implementations/go/" + p.Path); implemented != (p.Existing != "") {
			t.Errorf("%s: implemented=%t, relocation source %q", p.Path, implemented, p.Existing)
		}
	}
	for _, change := range []func(*ConsumerAPI){
		func(a *ConsumerAPI) { a.Commands[0].Owner = "rae" },
		func(a *ConsumerAPI) { a.Commands = nil },
		func(a *ConsumerAPI) { a.Commands[0].Name = "different" },
		func(a *ConsumerAPI) { a.Commands[0].EntryPoint = "internal/main" },
		func(a *ConsumerAPI) { a.Commands[0].Uses = nil },
		func(a *ConsumerAPI) { a.Commands[0].Uses = []string{"rae:missing"} },
		func(a *ConsumerAPI) { a.Commands = append(a.Commands, a.Commands[0]) },
		func(a *ConsumerAPI) { a.Modules[0].Module = "github.com/other/contracts" },
	} {
		m = consumerModel(t)
		change(m.ConsumerAPI)
		if !hasFinding(m.CheckDesign(), "ARCH-015", "consumer") {
			t.Error("changed executable or canonical module identity was accepted")
		}
	}
}

func TestConsumerAPIJSONRoundTrip(t *testing.T) {
	m := consumerModel(t)
	data, err := json.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	var copyModel Model
	if err := json.Unmarshal(data, &copyModel); err != nil {
		t.Fatal(err)
	}
	if got := copyModel.CheckDesign(); len(got) != 0 {
		t.Fatalf("round-trip design = %v", got)
	}
}

func TestConsumerAPIView(t *testing.T) {
	m := consumerModel(t)
	view := m.View()
	for _, want := range []string{"Planned public package", "github.com/OpenRAE/rae/implementations/go/contract/admission", "RUNTIME/runtime/control", "approval pending #1893", "| `raes` | runtime |", "<!-- go-consumer "} {
		if !strings.Contains(view, want) {
			t.Errorf("consumer view lacks %q", want)
		}
	}
	consumerPackage(t, m, "rae:sdl").Issues = []int{1782}
	if m.View() == view {
		t.Error("consumer delivery commitments are not bound to the view")
	}
}

func TestConsumerAPIApprovedRuntimeIdentity(t *testing.T) {
	for _, suffix := range []string{"", "/implementations/go"} {
		m := consumerModel(t)
		m.ConsumerAPI.Modules[1].Repository = "OpenRAE/example"
		m.ConsumerAPI.Modules[1].Module = "github.com/OpenRAE/example" + suffix
		if got := m.CheckDesign(); len(got) != 0 {
			t.Fatalf("approved runtime identity CheckDesign() = %v", got)
		}
	}
}

func TestConsumerAPIRequiredForProductModule(t *testing.T) {
	m := consumerModel(t)
	m.ConsumerAPI = nil
	if !hasFinding(m.CheckDesign(), "ARCH-015", "consumer") {
		t.Error("omitted consumer plan was accepted")
	}
}

func TestConsumerAPIRuntimeModulePaths(t *testing.T) {
	for _, suffix := range []string{"/internal/go", "/../other", "/bad path", "/.hidden"} {
		m := consumerModel(t)
		m.ConsumerAPI.Modules[1] = ConsumerModule{Owner: "runtime", Repository: "OpenRAE/example", Module: "github.com/OpenRAE/example" + suffix}
		if !hasFinding(m.CheckDesign(), "ARCH-015", "runtime consumer module") {
			t.Errorf("private or invalid runtime module suffix %q was accepted", suffix)
		}
	}
}

func TestConsumerAPIRelocationIdentity(t *testing.T) {
	for _, existing := range []string{"implementations/go/base/ingress", "implementations/go/internal/base/fault"} {
		m := consumerModel(t)
		consumerPackage(t, m, "rae:base/fault").Existing = existing
		if !hasFinding(m.CheckDesign(), "ARCH-015", "consumer relocation") {
			t.Errorf("relocation source %s was accepted", existing)
		}
	}
	m := consumerModel(t)
	for _, p := range m.ConsumerAPI.Packages {
		if p.Existing != "" && p.Existing != "implementations/go/"+p.Path {
			t.Errorf("%s keeps its implementation at %s, outside its public path", p.Path, p.Existing)
		}
	}
	m = consumerModel(t)
	consumerPackage(t, m, "rae:base/fault").Symbols = append(consumerPackage(t, m, "rae:base/fault").Symbols, "InventedExport")
	if err := m.CheckConsumerTypes(t.Context(), extractionRoot(t)); err == nil || !strings.Contains(err.Error(), "InventedExport") {
		t.Errorf("invented source export check = %v", err)
	}
}

func TestConsumerAPITypedDeclarations(t *testing.T) {
	m := consumerModel(t)
	if err := m.CheckConsumerTypes(t.Context(), extractionRoot(t)); err != nil {
		t.Fatal(err)
	}
}

// Implemented packages keep the one-way repository boundary: RAE consumer
// packages and entrypoints never reach runtime, and runtime reaches RAE only
// through implemented public RAE consumer packages.
func TestConsumerImportsStayOnTheRepositoryBoundary(t *testing.T) {
	const live = "implementations/go/internal/runtime/live"
	runtime := func(imports ...string) Package {
		return Package{Dir: live, Layer: "runtime", Doc: "live", Imports: imports}
	}
	addImport := func(m *Model, dir, dep string) {
		for i := range m.Packages {
			if m.Packages[i].Dir == dir {
				m.Packages[i].Imports = append(m.Packages[i].Imports, dep)
			}
		}
	}
	for _, tc := range []struct {
		name, problem string
		change        func(*Model)
	}{
		{"reverse import", "imports runtime package", func(m *Model) {
			m.Packages = append(m.Packages, runtime())
			addImport(m, "implementations/go/base/digest", live)
		}},
		{"indirect reverse import", "reaches runtime package " + live, func(m *Model) {
			m.Packages = append(m.Packages, runtime())
			addImport(m, "implementations/go/internal/base/value", live)
		}},
		{"rae entrypoint", "reaches runtime package " + live, func(m *Model) {
			m.Packages = append(m.Packages, runtime(), Package{Dir: "implementations/go/internal/adapter/bridge", Layer: "adapter", Doc: "bridge", Imports: []string{live}},
				Package{Dir: "implementations/go/cmd/raes-mcp", Layer: "command", Doc: "raes-mcp", Imports: []string{"implementations/go/internal/adapter/bridge"}})
		}},
		{"private import", "not an implemented public RAE consumer package", func(m *Model) {
			m.Packages = append(m.Packages, runtime("implementations/go/internal/base/jsonpointer"))
		}},
		{"runtime entrypoint", "not an implemented public RAE consumer package", func(m *Model) {
			m.Packages = append(m.Packages, Package{Dir: "implementations/go/cmd/raes", Layer: "command", Doc: "raes", Imports: []string{"implementations/go/internal/base/jsonpointer"}})
		}},
		{"hidden consumer package", "must be public", func(m *Model) {
			for i := range m.Packages {
				if m.Packages[i].Dir == "implementations/go/base/fault" {
					m.Packages[i].Public = false
				}
			}
		}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			m := consumerModel(t)
			tc.change(m)
			if got := m.checkConsumerImports(m.ConsumerAPI); !hasFinding(got, "ARCH-015", tc.problem) {
				t.Errorf("checkConsumerImports() = %v, want %q", got, tc.problem)
			}
		})
	}
	m := consumerModel(t)
	m.Packages = append(m.Packages, runtime("implementations/go/contract/binding"))
	if findings := m.checkConsumerImports(m.ConsumerAPI); len(findings) != 0 {
		t.Errorf("runtime import of a public RAE package: %v", findings)
	}
}

// Test files move with their package, so their imports keep the boundary too.
func TestConsumerTestImportsStayOnTheRepositoryBoundary(t *testing.T) {
	const live = "implementations/go/internal/runtime/live"
	for name, tc := range map[string]struct {
		from, dep, problem string
	}{
		"runtime test reaches a RAE helper": {live, "implementations/go/internal/base/jsonpointer", "a test file: runtime code imports"},
		"RAE test imports runtime":          {"implementations/go/base/digest", live, "a test file: the RAE package imports runtime"},
	} {
		t.Run(name, func(t *testing.T) {
			m := consumerModel(t)
			m.Packages = append(m.Packages, Package{Dir: live, Layer: "runtime", Doc: "live"})
			code := Code{Packages: map[string]Imports{tc.from: {Test: []string{tc.dep}}}}
			if got := m.checkConsumerTestImports(code); !hasFinding(got, "ARCH-015", tc.problem) {
				t.Errorf("checkConsumerTestImports() = %v, want %q", got, tc.problem)
			}
		})
	}
	m := consumerModel(t)
	m.Packages = append(m.Packages, Package{Dir: live, Layer: "runtime", Doc: "live"})
	if got := m.checkConsumerTestImports(Code{Packages: map[string]Imports{live: {Test: []string{"implementations/go/contract/binding"}}}}); len(got) != 0 {
		t.Errorf("runtime test import of a public RAE package: %v", got)
	}
}

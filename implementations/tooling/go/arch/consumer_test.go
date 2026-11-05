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
		{"escape", func(m *Model) { consumerPackage(t, m, "rae:sdl").Path = "../sdl" }},
		{"reverse", func(m *Model) { consumerPackage(t, m, "rae:sdl").Uses = []string{"runtime:runtime/control"} }},
		{"missing import", func(m *Model) { consumerPackage(t, m, "rae:sdl").Uses = []string{"rae:missing"} }},
		{"self import", func(m *Model) { consumerPackage(t, m, "rae:sdl").Uses = []string{"rae:sdl"} }},
		{"cycle", func(m *Model) { consumerPackage(t, m, "rae:contract/admission").Uses = []string{"rae:sdl"} }},
		{"reverse command", func(m *Model) { m.ConsumerAPI.Commands[1].Uses = []string{"runtime:runtime/control"} }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			m := consumerModel(t)
			tc.change(m)
			if !hasFinding(m.CheckDesign(), "ARCH-015", "consumer") {
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
	// Adding a plan must not declare absent public packages as implemented code.
	for _, p := range m.ConsumerAPI.Packages {
		if p.Existing != "" && !strings.Contains(p.Existing, "/internal/") {
			t.Errorf("source relocation is already claimed: %s", p.Existing)
		}
	}
	for _, change := range []func(*ConsumerAPI){
		func(a *ConsumerAPI) { a.Commands[0].Owner = "rae" },
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

package arch

import (
	"slices"
	"strings"
	"testing"
	"testing/fstest"
)

// validModel returns a model with one module, three layers, and packages that
// meet every design rule.
func validModel() *Model {
	return &Model{
		Schema:  Schema,
		Modules: []Module{{Dir: "m", Path: "example.com/m"}},
		Layers: []Layer{
			{Name: "base", Dir: "m/base", Doc: "base"},
			{Name: "core", Dir: "m/core", Doc: "core", Uses: []string{"base"}},
			{
				Name: "top", Dir: "m/top", Doc: "top", Uses: []string{"core", "base"},
				External: []External{{Path: "example.org/lib", Reason: "the library"}},
			},
		},
		Packages: []Package{
			{Dir: "m/base/clock", Layer: "base", Public: true, Doc: "clock"},
			{Dir: "m/base/hidden", Layer: "base", Doc: "hidden"},
			{Dir: "m/core/model", Layer: "core", Public: true, Doc: "model", Imports: []string{"m/base/clock"}},
			{Dir: "m/core/inner", Layer: "core", Doc: "inner", Imports: []string{"m/core/model"}},
			{Dir: "m/top/cli", Layer: "top", Doc: "cli", Imports: []string{"m/core/model", "m/base/clock"}},
		},
	}
}

type designCase struct {
	name    string
	change  func(*Model)
	rule    string
	problem string
}

// designCases returns one change of a valid model for each way in which a
// model can break a design rule, with the finding that the change causes.
func designCases() []designCase {
	return []designCase{
		{"duplicate module", func(m *Model) { m.Modules = append(m.Modules, m.Modules[0]) }, "ARCH-001", "unique"},
		{"module without path", func(m *Model) { m.Modules[0].Path = "" }, "ARCH-001", "module path"},
		{"module outside the repository", func(m *Model) { m.Modules[0].Dir = "../m" }, "ARCH-001", "relative directory"},
		{"duplicate layer", func(m *Model) { m.Layers = append(m.Layers, m.Layers[0]) }, "ARCH-002", "unique name"},
		{"layer without description", func(m *Model) { m.Layers[0].Doc = "" }, "ARCH-002", "description"},
		{"unclean layer directory", func(m *Model) { m.Layers[0].Dir = "m//base" }, "ARCH-002", "relative directory"},
		{"unknown used layer", func(m *Model) { m.Layers[1].Uses = []string{"missing"} }, "ARCH-002", `uses "missing"`},
		{"layer that uses itself", func(m *Model) { m.Layers[1].Uses = []string{"core"} }, "ARCH-002", `uses "core"`},
		{"layer cycle", func(m *Model) { m.Layers[0].Uses = []string{"top"} }, "ARCH-002", "base -> top -> core -> base"},
		{"duplicate package", func(m *Model) { m.Packages = append(m.Packages, m.Packages[0]) }, "ARCH-003", "unique"},
		{"package without description", func(m *Model) { m.Packages[0].Doc = "" }, "ARCH-003", "description"},
		{"package in an unknown layer", func(m *Model) { m.Packages[0].Layer = "missing" }, "ARCH-003", `layer "missing"`},
		{"package outside its layer", func(m *Model) { m.Packages[0].Dir = "m/core/clock" }, "ARCH-003", "outside m/base"},
		{"package outside every module", func(m *Model) { m.Modules[0].Dir = "other" }, "ARCH-003", "outside every declared module"},
		{"undeclared import", func(m *Model) { m.Packages[0].Imports = []string{"m/base/missing"} }, "ARCH-004", "does not declare"},
		{"self import", func(m *Model) { m.Packages[0].Imports = []string{"m/base/clock"} }, "ARCH-004", "imports itself"},
		{"import from a layer that is not used", func(m *Model) { m.Packages[0].Imports = []string{"m/core/model"} }, "ARCH-004", "may not use layer core"},
		{"import of a package that is not public", func(m *Model) { m.Packages[2].Imports = []string{"m/base/hidden"} }, "ARCH-004", "not public"},
		{"external standard library path", func(m *Model) { m.Layers[2].External[0].Path = "fmt" }, "ARCH-008", `"fmt"`},
		{"external path without reason", func(m *Model) { m.Layers[2].External[0].Reason = "" }, "ARCH-008", "a reason"},
		{"duplicate external path", func(m *Model) { m.Layers[2].External = append(m.Layers[2].External, m.Layers[2].External[0]) }, "ARCH-008", "unique path"},
	}
}

func TestCheckDesignAcceptsAValidModel(t *testing.T) {
	if findings := validModel().CheckDesign(); len(findings) != 0 {
		t.Errorf("CheckDesign() = %v, want no findings", findings)
	}
}

func TestCheckDesignReportsEachBrokenRule(t *testing.T) {
	for _, test := range designCases() {
		t.Run(test.name, func(t *testing.T) {
			model := validModel()
			test.change(model)
			if findings := model.CheckDesign(); !hasFinding(findings, test.rule, test.problem) {
				t.Errorf("CheckDesign() = %v, want a %s finding about %q with a fix", findings, test.rule, test.problem)
			}
		})
	}
}

// hasFinding reports whether findings has a finding of rule whose problem
// contains problem and that states a fix.
func hasFinding(findings []Finding, rule, problem string) bool {
	return slices.ContainsFunc(findings, func(f Finding) bool {
		return f.Rule == rule && strings.Contains(f.Problem, problem) && f.Fix != ""
	})
}

func TestFindingStringNamesTheRuleTheLocationAndTheFix(t *testing.T) {
	finding := Finding{Rule: "ARCH-005", Location: "m/x", Problem: "the problem.", Fix: "the fix."}
	if got, want := finding.String(), "ARCH-005 m/x: the problem. Fix: the fix."; got != want {
		t.Errorf("String() = %q, want %q", got, want)
	}
}

func TestLoadDecodesAValidModel(t *testing.T) {
	fsys := fstest.MapFS{"arch.json": {Data: []byte(`{"schema": "raes-go-architecture/v1", "modules": [], "layers": [], "packages": []}`)}}
	model, err := Load(fsys, "arch.json")
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if model.Schema != Schema {
		t.Errorf("Load() schema = %q, want %q", model.Schema, Schema)
	}
}

func TestLoadRejectsAnInvalidModel(t *testing.T) {
	tests := map[string]string{
		"unknown field":         `{"schema": "raes-go-architecture/v1", "extra": true}`,
		"unknown schema":        `{"schema": "other/v1"}`,
		"data after the model":  `{"schema": "raes-go-architecture/v1"} {}`,
		"brace after the model": `{"schema": "raes-go-architecture/v1"}}`,
		"not JSON":              `{`,
	}
	for name, content := range tests {
		t.Run(name, func(t *testing.T) {
			if _, err := Load(fstest.MapFS{"arch.json": {Data: []byte(content)}}, "arch.json"); err == nil {
				t.Error("Load() error = nil, want an error")
			}
		})
	}
	if _, err := Load(fstest.MapFS{}, "missing.json"); err == nil {
		t.Error("Load(missing.json) error = nil, want an error")
	}
}

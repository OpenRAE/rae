// Package arch checks the repository's Go code against its architecture model
// (ADR-122).
//
// The model declares the Go modules; the layers, each with the layers and the
// external packages that its packages may import; and each package, with its
// layer, its visibility to other layers, and its first-party imports. A design
// declares new or changed packages in the model before their code exists, and
// [Model.CheckDesign] validates it. [Model.CheckCode] validates the code against
// the model, and [CheckRules] validates the rule table of ADR-122. Each finding
// names its rule and location and states the change that fixes it.
package arch

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"path"
	"slices"
	"strings"
)

// Schema is the schema identifier of a valid model.
const Schema = "raes-go-architecture/v1"

// Model is the machine-readable architecture of the repository's Go code.
// Each directory in it is relative to the repository root.
type Model struct {
	Schema   string    `json:"schema"`
	Modules  []Module  `json:"modules"`
	Layers   []Layer   `json:"layers"`
	Packages []Package `json:"packages"`
}

// Module is a Go module: the directory that holds its go.mod, and its module path.
type Module struct {
	Dir  string `json:"dir"`
	Path string `json:"path"`
}

// Layer is a group of packages under one directory, with the layers and the
// external packages that its packages may import.
type Layer struct {
	Name     string     `json:"name"`
	Dir      string     `json:"dir"`
	Doc      string     `json:"doc"`
	Uses     []string   `json:"uses"`
	External []External `json:"external"`
}

// External permits the packages of a layer to import the packages under an
// import path outside the standard library and the declared modules.
type External struct {
	Path   string `json:"path"`
	Reason string `json:"reason"`
}

// Package is a Go package. A public package is visible to the layers that use
// its layer; a package is always visible inside its own layer.
type Package struct {
	Dir     string   `json:"dir"`
	Layer   string   `json:"layer"`
	Public  bool     `json:"public"`
	Doc     string   `json:"doc"`
	Imports []string `json:"imports"`
}

// Finding is one way in which the model, the code, or the rule table breaks a rule.
type Finding struct {
	Rule     string
	Location string
	Problem  string
	Fix      string
}

func (f Finding) String() string {
	return fmt.Sprintf("%s %s: %s Fix: %s", f.Rule, f.Location, f.Problem, f.Fix)
}

// Load reads a model. It rejects unknown fields, data after the model, and an
// unknown schema.
func Load(fsys fs.FS, name string) (*Model, error) {
	content, err := fs.ReadFile(fsys, name)
	if err != nil {
		return nil, err
	}
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	var model Model
	if err := decoder.Decode(&model); err != nil {
		return nil, fmt.Errorf("decode %s: %w", name, err)
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		return nil, fmt.Errorf("decode %s: data follows the model", name)
	}
	if model.Schema != Schema {
		return nil, fmt.Errorf("%s: schema is %q, want %q", name, model.Schema, Schema)
	}
	return &model, nil
}

// CheckDesign checks the rules that the model must meet on its own, before any
// code exists.
func (m *Model) CheckDesign() []Finding {
	return slices.Concat(m.checkModules(), m.checkLayers(), m.checkExternal(), m.checkPackages(), m.checkImports())
}

func (m *Model) checkModules() []Finding {
	var findings []Finding
	dirs, paths := map[string]bool{}, map[string]bool{}
	for _, module := range m.Modules {
		if !isRepoDir(module.Dir) || module.Path == "" || dirs[module.Dir] || paths[module.Path] {
			findings = append(findings, Finding{
				Rule: ruleModules, Location: module.Dir,
				Problem: "the module needs a unique clean relative directory and a unique module path.",
				Fix:     "correct or remove the module entry in the model.",
			})
		}
		dirs[module.Dir], paths[module.Path] = true, true
	}
	return findings
}

func (m *Model) checkLayers() []Finding {
	var findings []Finding
	names := map[string]bool{}
	for _, layer := range m.Layers {
		if layer.Name == "" || names[layer.Name] || !isRepoDir(layer.Dir) || layer.Doc == "" {
			findings = append(findings, Finding{
				Rule: ruleLayers, Location: layer.Dir,
				Problem: fmt.Sprintf("layer %q needs a unique name, a clean relative directory, and a description.", layer.Name),
				Fix:     "correct the layer entry in the model.",
			})
		}
		names[layer.Name] = true
	}
	for _, layer := range m.Layers {
		for _, used := range layer.Uses {
			if !names[used] || used == layer.Name {
				findings = append(findings, Finding{
					Rule: ruleLayers, Location: layer.Dir,
					Problem: fmt.Sprintf("layer %q uses %q, which is not another declared layer.", layer.Name, used),
					Fix:     "name a declared layer, or remove the entry from uses.",
				})
			}
		}
	}
	if cycle := m.layerCycle(); cycle != nil {
		findings = append(findings, Finding{
			Rule: ruleLayers, Location: m.layer(cycle[0]).Dir,
			Problem: "the layers " + strings.Join(cycle, " -> ") + " use each other in a cycle.",
			Fix:     "remove one use so that the layer graph has no cycle.",
		})
	}
	return findings
}

// layerCycle returns the layers of one cycle in the uses graph, or nil.
func (m *Model) layerCycle() []string {
	const (
		visiting = iota + 1 // The zero state is unvisited.
		done
	)
	state := map[string]int{}
	var stack []string
	var visit func(name string) []string
	visit = func(name string) []string {
		switch state[name] {
		case visiting:
			return append(slices.Clone(stack[slices.Index(stack, name):]), name)
		case done:
			return nil
		}
		state[name] = visiting
		stack = append(stack, name)
		for _, used := range m.layer(name).Uses {
			if cycle := visit(used); cycle != nil {
				return cycle
			}
		}
		stack = stack[:len(stack)-1]
		state[name] = done
		return nil
	}
	for _, layer := range m.Layers {
		if cycle := visit(layer.Name); cycle != nil {
			return cycle
		}
	}
	return nil
}

func (m *Model) checkExternal() []Finding {
	var findings []Finding
	for _, layer := range m.Layers {
		paths := map[string]bool{}
		for _, external := range layer.External {
			if isStandard(external.Path) || external.Reason == "" || paths[external.Path] {
				findings = append(findings, Finding{
					Rule: ruleExternal, Location: layer.Dir,
					Problem: fmt.Sprintf("the external entry %q of layer %s needs a unique path outside the standard library and a reason.", external.Path, layer.Name),
					Fix:     "correct or remove the external entry in the model.",
				})
			}
			paths[external.Path] = true
		}
	}
	return findings
}

func (m *Model) checkPackages() []Finding {
	var findings []Finding
	dirs := map[string]bool{}
	for _, pkg := range m.Packages {
		if problem, fix := m.packageProblem(pkg, dirs[pkg.Dir]); problem != "" {
			findings = append(findings, Finding{Rule: rulePackages, Location: pkg.Dir, Problem: problem, Fix: fix})
		}
		dirs[pkg.Dir] = true
	}
	return findings
}

// packageProblem describes why the entry of pkg breaks ARCH-003, with its fix.
// A duplicate entry repeats the directory of an earlier entry.
func (m *Model) packageProblem(pkg Package, duplicate bool) (problem, fix string) {
	if !isRepoDir(pkg.Dir) || duplicate || pkg.Doc == "" {
		return "the package needs a unique clean relative directory and a description.",
			"correct the package entry in the model."
	}
	layer := m.layer(pkg.Layer)
	if layer.Name == "" {
		return fmt.Sprintf("the package names layer %q, which the model does not declare.", pkg.Layer),
			"assign the package to a declared layer."
	}
	if !within(pkg.Dir, layer.Dir) {
		return fmt.Sprintf("the package is outside %s, the directory of its layer %s.", layer.Dir, layer.Name),
			fmt.Sprintf("move the package under %s, or assign it to the layer that owns its directory.", layer.Dir)
	}
	if !slices.ContainsFunc(m.Modules, func(module Module) bool { return within(pkg.Dir, module.Dir) }) {
		return "the package is outside every declared module.",
			"declare the module that holds the package, or move the package into a declared module."
	}
	return "", ""
}

func (m *Model) checkImports() []Finding {
	var findings []Finding
	for _, pkg := range m.Packages {
		for _, imported := range pkg.Imports {
			if problem, fix := m.importProblem(pkg, imported); problem != "" {
				findings = append(findings, Finding{Rule: ruleDeclaredImports, Location: pkg.Dir, Problem: problem, Fix: fix})
			}
		}
	}
	return findings
}

// importProblem describes why from may not import the package in dir, with its fix.
func (m *Model) importProblem(from Package, dir string) (problem, fix string) {
	target, ok := m.pkg(dir)
	if !ok {
		return fmt.Sprintf("the package imports %s, which the model does not declare.", dir),
			"declare the imported package in the model first."
	}
	if target.Dir == from.Dir {
		return "the package imports itself.", "remove the import."
	}
	if target.Layer == from.Layer {
		return "", ""
	}
	if !slices.Contains(m.layer(from.Layer).Uses, target.Layer) {
		return fmt.Sprintf("layer %s may not use layer %s, which owns %s.", from.Layer, target.Layer, dir),
			"move the needed code to a layer that this layer uses, or change the layer model through the design step."
	}
	if !target.Public {
		return dir + " is not public to other layers.",
			"use a public package of that layer, or mark the package public through the design step."
	}
	return "", ""
}

func (m *Model) layer(name string) Layer {
	for _, layer := range m.Layers {
		if layer.Name == name {
			return layer
		}
	}
	return Layer{}
}

func (m *Model) pkg(dir string) (Package, bool) {
	for _, pkg := range m.Packages {
		if pkg.Dir == dir {
			return pkg, true
		}
	}
	return Package{}, false
}

// isRepoDir reports whether dir is a clean, relative, slash-separated path inside the repository.
func isRepoDir(dir string) bool {
	return dir != "" && dir == path.Clean(dir) && !path.IsAbs(dir) && dir != "." && !strings.HasPrefix(dir, "../")
}

// isStandard reports whether an import path can name a standard library
// package: the first element of every other import path contains a dot.
func isStandard(importPath string) bool {
	first, _, _ := strings.Cut(importPath, "/")
	return !strings.Contains(first, ".")
}

// within reports whether the slash-separated path name is root or is below it.
func within(name, root string) bool {
	return name == root || strings.HasPrefix(name, root+"/")
}

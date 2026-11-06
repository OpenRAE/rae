package arch

import (
	"context"
	"errors"
	"fmt"
	"go/build"
	"io/fs"
	"maps"
	"os"
	"path"
	"path/filepath"
	"slices"
	"strings"

	"golang.org/x/mod/modfile"
)

// Code is the Go code in the repository.
type Code struct {
	// Modules maps the directory of each go.mod file to the module path that it states.
	Modules map[string]string
	// Packages maps the directory of each package in a declared module to its imports.
	Packages map[string]Imports
	// Replaced lists the directories of the go.mod files that state a replace directive.
	Replaced []string
}

// Imports are the imports of one package outside the standard library.
type Imports struct {
	// Code are the first-party packages that the non-test files import.
	Code []string
	// Test are the other first-party packages that the test files import.
	Test []string
	// External are the import paths outside the declared modules that any
	// file of the package imports.
	External []string
}

// LoadCode finds the Go modules of the repository at root and reads the
// imports of each package of each module that the model declares. It reads
// each Go file whatever its build constraints, so the code of each platform
// and build tag meets the model.
func LoadCode(ctx context.Context, root string, model *Model) (Code, error) {
	modules, replaced, err := findModules(os.DirFS(root))
	if err != nil {
		return Code{}, err
	}
	code := Code{Modules: modules, Packages: map[string]Imports{}, Replaced: replaced}
	for _, module := range model.Modules {
		if modules[module.Dir] != module.Path {
			continue // CheckCode reports the missing or different module.
		}
		if err := model.readModule(ctx, root, module.Dir, modules, code.Packages); err != nil {
			return Code{}, err
		}
	}
	for dir, imports := range code.Packages {
		imports.Code = sortedUnique(imports.Code)
		imports.Test = difference(sortedUnique(imports.Test), imports.Code)
		imports.External = sortedUnique(imports.External)
		code.Packages[dir] = imports
	}
	return code, nil
}

// readModule records the imports of each package of the module in dir. It
// leaves out the directories that the go command ignores and nested modules.
func (m *Model) readModule(ctx context.Context, root, dir string, modules map[string]string, found map[string]Imports) error {
	reader := build.Default
	reader.UseAllFiles = true
	return fs.WalkDir(os.DirFS(root), dir, func(name string, entry fs.DirEntry, err error) error {
		if err != nil || !entry.IsDir() {
			return err
		}
		if _, nested := modules[name]; name != dir && (nested || ignoredDir(entry.Name())) {
			return fs.SkipDir
		}
		if err = ctx.Err(); err != nil {
			return err
		}
		pkg, err := reader.ImportDir(filepath.Join(root, filepath.FromSlash(name)), 0)
		if _, empty := errors.AsType[*build.NoGoError](err); empty {
			return nil
		}
		if err != nil {
			return fmt.Errorf("load %s: %w", name, err)
		}
		m.addPackage(found, name, pkg)
		return nil
	})
}

// findModules maps the directory of each go.mod file in the repository to the
// module path that it states, and lists the go.mod files that replace a module.
// Like the go command, it skips testdata directories and the directories whose
// names start with a dot or an underscore.
func findModules(repo fs.FS) (modules map[string]string, replaced []string, err error) {
	modules = map[string]string{}
	err = fs.WalkDir(repo, ".", func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if name != "." && ignoredDir(entry.Name()) {
				return fs.SkipDir
			}
			return nil
		}
		if entry.Name() != "go.mod" {
			return nil
		}
		file, err := readModFile(repo, name)
		if err != nil {
			return err
		}
		modules[path.Dir(name)] = file.Module.Mod.Path
		if len(file.Replace) > 0 {
			replaced = append(replaced, path.Dir(name))
		}
		return nil
	})
	return modules, replaced, err
}

// readModFile parses the go.mod file at name.
func readModFile(repo fs.FS, name string) (*modfile.File, error) {
	content, err := fs.ReadFile(repo, name)
	if err != nil {
		return nil, err
	}
	file, err := modfile.Parse(name, content, nil)
	if err != nil {
		return nil, err
	}
	if file.Module == nil {
		return nil, fmt.Errorf("%s: no module directive", name)
	}
	return file, nil
}

// ignoredDir reports whether the go command ignores a directory with this
// name: testdata, and each name that starts with a dot or an underscore.
func ignoredDir(name string) bool {
	return name == "testdata" || strings.HasPrefix(name, ".") || strings.HasPrefix(name, "_")
}

// addPackage records the imports of the package in dir and of its tests.
func (m *Model) addPackage(found map[string]Imports, dir string, pkg *build.Package) {
	imports := found[dir]
	add := func(list *[]string, importPaths []string) {
		for _, importPath := range importPaths {
			target, firstParty := m.dirOf(importPath)
			if !firstParty && !isStandard(importPath) {
				imports.External = append(imports.External, importPath)
			}
			// An external test imports the package under test.
			if firstParty && target != dir {
				*list = append(*list, target)
			}
		}
	}
	add(&imports.Code, pkg.Imports)
	add(&imports.Test, pkg.TestImports)
	add(&imports.Test, pkg.XTestImports)
	found[dir] = imports
}

// dirOf returns the repository directory of a first-party import path. The
// innermost module whose path contains the import path owns it.
func (m *Model) dirOf(importPath string) (string, bool) {
	var owner *Module
	for i := range m.Modules {
		module := &m.Modules[i]
		if within(importPath, module.Path) && (owner == nil || within(module.Path, owner.Path)) {
			owner = module
		}
	}
	if owner == nil {
		return "", false
	}
	return owner.Dir + strings.TrimPrefix(importPath, owner.Path), true
}

// CheckCode checks the code against the model.
func (m *Model) CheckCode(code Code) []Finding {
	return slices.Concat(m.checkModuleFiles(code), m.checkDeclared(code), m.checkCodeImports(code), m.checkExternalImports(code), m.checkConsumerTestImports(code))
}

func (m *Model) checkModuleFiles(code Code) []Finding {
	var findings []Finding
	for _, dir := range slices.Sorted(maps.Keys(code.Modules)) {
		i := slices.IndexFunc(m.Modules, func(module Module) bool { return module.Dir == dir })
		if i < 0 {
			findings = append(findings, Finding{
				Rule: ruleModules, Location: dir + "/go.mod",
				Problem: "the model does not declare this Go module.",
				Fix:     "declare the module and its packages in the model through the design step.",
			})
			continue
		}
		if m.Modules[i].Path != code.Modules[dir] {
			findings = append(findings, Finding{
				Rule: ruleModules, Location: dir + "/go.mod",
				Problem: fmt.Sprintf("the go.mod states module path %q, but the model declares %q.", code.Modules[dir], m.Modules[i].Path),
				Fix:     "make the module path in the model and in the go.mod the same.",
			})
		}
	}
	for _, dir := range code.Replaced {
		findings = append(findings, Finding{
			Rule: ruleModules, Location: dir + "/go.mod",
			Problem: "the go.mod states a replace directive, which released module metadata must not carry.",
			Fix:     "remove the replace directive; resolve the dependency from a pinned published version.",
		})
	}
	for _, module := range m.Modules {
		if _, ok := code.Modules[module.Dir]; !ok {
			findings = append(findings, Finding{
				Rule: ruleModules, Location: module.Dir,
				Problem: "the model declares a module that has no go.mod.",
				Fix:     "add the module, or remove it from the model.",
			})
		}
	}
	return findings
}

func (m *Model) checkDeclared(code Code) []Finding {
	var findings []Finding
	for _, dir := range slices.Sorted(maps.Keys(code.Packages)) {
		if _, ok := m.pkg(dir); !ok {
			findings = append(findings, Finding{
				Rule: ruleClassified, Location: dir,
				Problem: "the model does not declare this package.",
				Fix:     "declare the package, its layer, and its imports in the model through the design step.",
			})
		}
	}
	for _, pkg := range m.Packages {
		if _, ok := code.Packages[pkg.Dir]; !ok {
			findings = append(findings, Finding{
				Rule: ruleClassified, Location: pkg.Dir,
				Problem: "the model declares a package that has no code.",
				Fix:     "add the package, or remove it from the model.",
			})
		}
	}
	return findings
}

func (m *Model) checkCodeImports(code Code) []Finding {
	var findings []Finding
	for _, pkg := range m.Packages {
		imports, ok := code.Packages[pkg.Dir]
		if !ok {
			continue // checkDeclared reports the package.
		}
		for _, missing := range difference(imports.Code, pkg.Imports) {
			findings = append(findings, Finding{
				Rule: ruleCodeImports, Location: pkg.Dir,
				Problem: fmt.Sprintf("the code imports %s, which the model does not declare for this package.", missing),
				Fix:     "declare the import in the model through the design step, or remove it from the code.",
			})
		}
		for _, unused := range difference(pkg.Imports, imports.Code) {
			findings = append(findings, Finding{
				Rule: ruleCodeImports, Location: pkg.Dir,
				Problem: fmt.Sprintf("the model declares an import of %s that the code does not use.", unused),
				Fix:     "remove the import from the model.",
			})
		}
		for _, imported := range imports.Test {
			if problem, fix := m.importProblem(pkg, imported); problem != "" {
				findings = append(findings, Finding{Rule: ruleTestImports, Location: pkg.Dir, Problem: "a test file: " + problem, Fix: fix})
			}
		}
	}
	return findings
}

func (m *Model) checkExternalImports(code Code) []Finding {
	var findings []Finding
	used := map[[2]string]bool{} // Each used layer name and external path.
	for _, pkg := range m.Packages {
		layer := m.layer(pkg.Layer)
		for _, imported := range code.Packages[pkg.Dir].External {
			i := slices.IndexFunc(layer.External, func(external External) bool { return within(imported, external.Path) })
			if i < 0 {
				findings = append(findings, Finding{
					Rule: ruleExternal, Location: pkg.Dir,
					Problem: fmt.Sprintf("the package imports %s, which layer %s does not list as external.", imported, layer.Name),
					Fix:     "list the import path and a reason in the external entries of the layer through the design step, or remove the import.",
				})
				continue
			}
			used[[2]string{layer.Name, layer.External[i].Path}] = true
		}
	}
	for _, layer := range m.Layers {
		for _, external := range layer.External {
			if !used[[2]string{layer.Name, external.Path}] {
				findings = append(findings, Finding{
					Rule: ruleExternal, Location: layer.Dir,
					Problem: fmt.Sprintf("layer %s lists the external path %s, which no package of the layer imports.", layer.Name, external.Path),
					Fix:     "remove the external entry from the model.",
				})
			}
		}
	}
	return findings
}

// difference returns the elements of a that b does not contain.
func difference(a, b []string) []string {
	return slices.DeleteFunc(slices.Clone(a), func(item string) bool { return slices.Contains(b, item) })
}

func sortedUnique(items []string) []string {
	slices.Sort(items)
	return slices.Compact(items)
}

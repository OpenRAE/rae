package arch

import (
	"context"
	"fmt"
	"io/fs"
	"maps"
	"os"
	"path"
	"path/filepath"
	"slices"
	"strings"

	"golang.org/x/mod/modfile"
	"golang.org/x/tools/go/packages"
)

// Code is the Go code in the repository.
type Code struct {
	// Modules maps the directory of each go.mod file to the module path that it states.
	Modules map[string]string
	// Packages maps the directory of each package in a declared module to its imports.
	Packages map[string]Imports
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

// LoadCode finds the Go modules of the repository at root and loads the
// packages of each module that the model declares.
func LoadCode(ctx context.Context, root string, model *Model) (Code, error) {
	modules, err := findModules(os.DirFS(root))
	if err != nil {
		return Code{}, err
	}
	code := Code{Modules: modules, Packages: map[string]Imports{}}
	for _, module := range model.Modules {
		if modules[module.Dir] != module.Path {
			continue // CheckCode reports the missing or different module.
		}
		config := &packages.Config{
			Context: ctx,
			Dir:     filepath.Join(root, filepath.FromSlash(module.Dir)),
			Mode:    packages.NeedName | packages.NeedImports,
			Tests:   true,
		}
		loaded, err := packages.Load(config, "./...")
		if err != nil {
			return Code{}, fmt.Errorf("load %s: %w", module.Dir, err)
		}
		for _, pkg := range loaded {
			if err := model.addPackage(code.Packages, module, pkg); err != nil {
				return Code{}, err
			}
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

// findModules maps the directory of each go.mod file in the repository to the
// module path that it states. Like the go command, it skips testdata
// directories and the directories whose names start with a dot or an
// underscore.
func findModules(repo fs.FS) (map[string]string, error) {
	modules := map[string]string{}
	err := fs.WalkDir(repo, ".", func(name string, entry fs.DirEntry, err error) error {
		switch {
		case err != nil:
			return err
		case entry.IsDir() && name != "." && (entry.Name() == "testdata" || strings.ContainsAny(entry.Name()[:1], "._")):
			return fs.SkipDir
		case !entry.IsDir() && entry.Name() == "go.mod":
			content, err := fs.ReadFile(repo, name)
			if err != nil {
				return err
			}
			modules[path.Dir(name)] = modfile.ModulePath(content)
		}
		return nil
	})
	return modules, err
}

// addPackage records the imports of a package of module, or of a test variant
// of the package. It skips the generated test main packages and the packages
// that a test recompiles, because their files belong to other packages.
func (m *Model) addPackage(found map[string]Imports, module Module, pkg *packages.Package) error {
	if len(pkg.Errors) > 0 {
		return fmt.Errorf("load %s: %w", pkg.ID, pkg.Errors[0])
	}
	owner := strings.TrimSuffix(pkg.PkgPath, "_test")
	isTest := pkg.ID != pkg.PkgPath
	if strings.HasSuffix(pkg.ID, ".test") || isTest && !strings.HasSuffix(pkg.ID, " ["+owner+".test]") {
		return nil
	}
	dir := module.Dir + strings.TrimPrefix(owner, module.Path)
	imports := found[dir]
	for importPath := range pkg.Imports {
		target, firstParty := m.dirOf(importPath)
		switch {
		case firstParty && target == dir: // An external test imports the package under test.
		case firstParty && isTest:
			imports.Test = append(imports.Test, target)
		case firstParty:
			imports.Code = append(imports.Code, target)
		case !isStandard(importPath):
			imports.External = append(imports.External, importPath)
		}
	}
	found[dir] = imports
	return nil
}

// dirOf returns the repository directory of a first-party import path. The
// longest module path that contains the import path selects the module.
func (m *Model) dirOf(importPath string) (string, bool) {
	var owner *Module
	for i, module := range m.Modules {
		if within(importPath, module.Path) && (owner == nil || len(module.Path) > len(owner.Path)) {
			owner = &m.Modules[i]
		}
	}
	if owner == nil {
		return "", false
	}
	return owner.Dir + strings.TrimPrefix(importPath, owner.Path), true
}

// CheckCode checks the code against the model.
func (m *Model) CheckCode(code Code) []Finding {
	return slices.Concat(m.checkModuleFiles(code), m.checkDeclared(code), m.checkCodeImports(code), m.checkExternalImports(code))
}

func (m *Model) checkModuleFiles(code Code) []Finding {
	var findings []Finding
	for _, dir := range slices.Sorted(maps.Keys(code.Modules)) {
		i := slices.IndexFunc(m.Modules, func(module Module) bool { return module.Dir == dir })
		switch {
		case i < 0:
			findings = append(findings, Finding{
				Rule: ruleModules, Location: dir + "/go.mod",
				Problem: "the model does not declare this Go module.",
				Fix:     "declare the module and its packages in the model through the design step.",
			})
		case m.Modules[i].Path != code.Modules[dir]:
			findings = append(findings, Finding{
				Rule: ruleModules, Location: dir + "/go.mod",
				Problem: fmt.Sprintf("the go.mod states module path %q, but the model declares %q.", code.Modules[dir], m.Modules[i].Path),
				Fix:     "make the module path in the model and in the go.mod the same.",
			})
		}
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

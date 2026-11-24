package arch

import (
	"context"
	"fmt"
	"go/ast"
	"go/importer"
	"go/parser"
	"go/token"
	"go/types"
	"io"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"slices"
	"strconv"
	"strings"

	"golang.org/x/tools/go/packages"
)

type consumerTypes struct {
	model        *Model
	repo         fs.FS
	existing     map[string]*types.Package
	checked      map[string]*types.Package
	loading      map[string]bool
	standard     types.Importer
	remaining    int
	declarations map[string]consumerDeclaration
}
type consumerDeclaration struct {
	file *ast.File
	fset *token.FileSet
}

// CheckConsumerTypes checks the planned declarations with Go's type checker.
// It loads existing owners and declared standard roots offline without executing product code.
func (m *Model) CheckConsumerTypes(ctx context.Context, root string) error {
	if m.ConsumerAPI == nil {
		return nil
	}
	if findings := m.CheckDesign(); len(findings) > 0 {
		return fmt.Errorf("invalid consumer design: %s", findings[0])
	}
	legacyModel := &Model{}
	for _, module := range m.Modules {
		if module.Dir == consumerProductDir {
			legacyModel.Modules = append(legacyModel.Modules, module)
		}
	}
	for _, p := range m.ConsumerAPI.Packages {
		if p.Existing != "" {
			source, _ := m.pkg(p.Existing)
			legacyModel.Packages = append(legacyModel.Packages, source)
		}
	}
	if err := validateAPITree(root, legacyModel); err != nil {
		return err
	}
	rooted, err := os.OpenRoot(root)
	if err != nil {
		return err
	}
	defer func() { _ = rooted.Close() }()
	c := newConsumerTypes(m, rooted.FS())
	standard, err := c.standardImports()
	if err != nil {
		return err
	}
	c.existing, err = m.loadConsumerExisting(ctx, root, standard...)
	if err != nil {
		return err
	}
	return c.checkPackages()
}

func (m *Model) loadConsumerExisting(ctx context.Context, root string, standard ...string) (map[string]*types.Package, error) {
	var patterns []string
	for _, p := range m.ConsumerAPI.Packages {
		if p.Existing != "" {
			patterns = append(patterns, "./"+strings.TrimPrefix(p.Existing, consumerProductDir+"/"))
		}
	}
	patterns = append(patterns, standard...)
	if len(patterns) == 0 {
		return map[string]*types.Package{}, nil
	}
	loaded, err := packages.Load(&packages.Config{Context: ctx, Dir: filepath.Join(root, consumerProductDir), Mode: packages.LoadTypes | packages.NeedDeps, Env: append(os.Environ(), "GOWORK=off", "GOPROXY=off", "GOSUMDB=off", "GOTOOLCHAIN=local", "GOFLAGS=-mod=readonly", "GOPACKAGESDRIVER=off", "CGO_ENABLED=0", "GO111MODULE=on")}, patterns...)
	if err != nil {
		return nil, fmt.Errorf("load existing consumer types: %w", err)
	}
	result, err := consumerStandardPackages(loaded)
	if err != nil {
		return nil, err
	}
	for _, p := range loaded {
		for _, q := range m.ConsumerAPI.Packages {
			if strings.HasSuffix(p.PkgPath, strings.TrimPrefix(q.Existing, consumerProductDir)) && q.Existing != "" {
				result[m.consumerImport(q)] = p.Types
			}
		}
	}
	return result, nil
}

func consumerStandardPackages(loaded []*packages.Package) (map[string]*types.Package, error) {
	result := map[string]*types.Package{}
	var dependencyError error
	packages.Visit(loaded, nil, func(p *packages.Package) {
		if dependencyError == nil && len(p.Errors) > 0 {
			dependencyError = p.Errors[0]
		}
		if p.Types != nil && isStandard(p.PkgPath) {
			result[p.PkgPath] = p.Types
		}
	})
	if dependencyError != nil {
		return nil, fmt.Errorf("load existing consumer types: %w", dependencyError)
	}
	return result, nil
}

func (m *Model) consumerImport(p ConsumerPackage) string {
	prefix := "RUNTIME"
	for _, module := range m.ConsumerAPI.Modules {
		if module.Owner == p.Owner && module.Module != "" {
			prefix = module.Module
		}
	}
	return prefix + "/" + p.Path
}

func newConsumerTypes(m *Model, repo fs.FS) *consumerTypes {
	return &consumerTypes{model: m, repo: repo, checked: map[string]*types.Package{}, loading: map[string]bool{}, standard: importer.Default(), remaining: 4 * 1024 * 1024, declarations: map[string]consumerDeclaration{}}
}

func (c *consumerTypes) checkPackages() error {
	for _, p := range c.model.ConsumerAPI.Packages {
		checked, err := c.Import(c.model.consumerImport(p))
		if err != nil {
			return err
		}
		for _, name := range p.Symbols {
			if !consumerTypeSymbol(checked, name) {
				return fmt.Errorf("ARCH-015 %s: consumer identifier %s has no typed declaration", p.Path, name)
			}
		}
	}
	return c.checkImplementedContracts()
}

func (c *consumerTypes) readDeclaration(p ConsumerPackage) (*ast.File, *token.FileSet, error) {
	key := p.Owner + ":" + p.Path
	if d, ok := c.declarations[key]; ok {
		return d.file, d.fset, nil
	}
	file, fset, err := readConsumerDeclaration(c.repo, p, &c.remaining)
	if err != nil {
		return nil, nil, err
	}
	if c.declarations == nil {
		c.declarations = map[string]consumerDeclaration{}
	}
	c.declarations[key] = consumerDeclaration{file: file, fset: fset}
	return file, fset, nil
}

// Load the declared standard roots with legacy owners so their transitive
// named types share one package universe. Reuse the bounded, hashed parse.
func (c *consumerTypes) standardImports() ([]string, error) {
	var names []string
	for _, p := range c.model.ConsumerAPI.Packages {
		if p.Declarations == "" {
			continue
		}
		file, _, err := c.readDeclaration(p)
		if err != nil {
			return nil, err
		}
		if err = c.checkImports(p, file); err != nil {
			return nil, err
		}
		for _, spec := range file.Imports {
			name, _ := strconv.Unquote(spec.Path.Value)
			if isStandard(name) && !strings.HasPrefix(name, "RUNTIME/") {
				names = append(names, name)
			}
		}
	}
	slices.Sort(names)
	return slices.Compact(names), nil
}

func consumerTypeSymbol(p *types.Package, name string) bool {
	receiver, method, hasMethod := strings.Cut(name, ".")
	object := p.Scope().Lookup(receiver)
	if object == nil {
		return false
	}
	if !hasMethod {
		return object.Exported()
	}
	return types.NewMethodSet(types.NewPointer(object.Type())).Lookup(p, method) != nil || types.NewMethodSet(object.Type()).Lookup(p, method) != nil
}

func (c *consumerTypes) Import(name string) (*types.Package, error) {
	if p := c.checked[name]; p != nil {
		return p, nil
	}
	if c.loading[name] {
		return nil, fmt.Errorf("ARCH-015 %s: consumer declaration import cycle", name)
	}
	var entry *ConsumerPackage
	for i := range c.model.ConsumerAPI.Packages {
		p := &c.model.ConsumerAPI.Packages[i]
		if c.model.consumerImport(*p) == name {
			entry = p
			break
		}
	}
	if entry == nil {
		if !isStandard(name) || strings.HasPrefix(name, "RUNTIME/") {
			return nil, fmt.Errorf("ARCH-015 %s: undeclared consumer import", name)
		}
		if p := c.existing[name]; p != nil {
			return p, nil
		}
		return c.standard.Import(name)
	}
	return c.checkPackage(name, *entry)
}

func (c *consumerTypes) checkPackage(name string, entry ConsumerPackage) (*types.Package, error) {
	legacy := c.existing[name]
	if entry.Declarations == "" {
		if legacy == nil {
			return nil, fmt.Errorf("ARCH-015 %s: consumer API has neither declarations nor an existing typed owner", name)
		}
		c.checked[name] = legacy
		return legacy, nil
	}
	file, fset, err := c.readDeclaration(entry)
	if err != nil {
		return nil, err
	}
	if err = c.checkImports(entry, file); err != nil {
		return nil, err
	}
	pkg := types.NewPackage(name, file.Name.Name)
	declared := declaredNames(file)
	if legacy != nil {
		for _, symbol := range legacy.Scope().Names() {
			object := legacy.Scope().Lookup(symbol)
			if object.Exported() && !declared[symbol] {
				pkg.Scope().Insert(object)
			}
		}
	}
	c.loading[name] = true
	defer delete(c.loading, name)
	checker := types.NewChecker(&types.Config{Importer: c, IgnoreFuncBodies: true}, fset, pkg, nil)
	if err = checker.Files([]*ast.File{file}); err != nil {
		return nil, fmt.Errorf("ARCH-015 %s: invalid typed consumer declaration: %w", entry.Declarations, err)
	}
	c.checked[name] = pkg
	return pkg, nil
}

// declaredNames returns the package-level names that a declaration file declares.
func declaredNames(file *ast.File) map[string]bool {
	names := map[string]bool{}
	for _, decl := range file.Decls {
		if fn, ok := decl.(*ast.FuncDecl); ok && fn.Recv == nil {
			names[fn.Name.Name] = true
		}
		if block, ok := decl.(*ast.GenDecl); ok {
			for _, spec := range block.Specs {
				for _, name := range specNames(spec) {
					names[name] = true
				}
			}
		}
	}
	return names
}

// specNames returns the names that a type, constant or variable spec declares.
func specNames(spec ast.Spec) []string {
	if typeSpec, ok := spec.(*ast.TypeSpec); ok {
		return []string{typeSpec.Name.Name}
	}
	var names []string
	if value, ok := spec.(*ast.ValueSpec); ok {
		for _, ident := range value.Names {
			names = append(names, ident.Name)
		}
	}
	return names
}

// checkExtensions compares each declared extension that a build configuration
// of an existing package implements with its declaration. An extension that a
// configuration does not implement stays planned.
func (c *consumerTypes) checkExtensions(planned ConsumerPackage, actual Package) error {
	file, _, err := c.readDeclaration(planned)
	if err != nil {
		return err
	}
	name := c.model.consumerImport(planned)
	checked := c.checked[name]
	for config, snapshot := range actual.API {
		have := c.normalizeAPI(snapshot)
		for symbol := range declaredNames(file) {
			if !implementsObject(have, name, symbol) {
				continue
			}
			for _, line := range c.normalizeAPI(objectAPI(checked.Scope().Lookup(symbol))) {
				if _, found := slices.BinarySearch(have, line); !found {
					return fmt.Errorf("ARCH-015 %s: %s implements %s differently from its typed consumer contract", actual.Dir, config, symbol)
				}
			}
		}
	}
	return nil
}

// implementsObject reports whether a sorted API snapshot declares the
// package-level object symbol of the package path.
func implementsObject(api []string, path, symbol string) bool {
	qualified := path + "." + symbol
	return slices.ContainsFunc(api, func(line string) bool {
		for _, kind := range []string{"func ", "type ", "var ", "const "} {
			rest, ok := strings.CutPrefix(line, kind+qualified)
			if ok && (rest == "" || strings.ContainsAny(rest[:1], " ([")) {
				return true
			}
		}
		return false
	})
}

func readConsumerDeclaration(repo fs.FS, p ConsumerPackage, remaining *int) (*ast.File, *token.FileSet, error) {
	name := p.Declarations
	if !fs.ValidPath(name) || !strings.HasPrefix(name, "implementations/architecture-api/planned/") || !strings.HasSuffix(name, ".go.txt") {
		return nil, nil, fmt.Errorf("ARCH-015 %s: unsafe consumer declaration path", name)
	}
	f, err := repo.Open(name)
	if err != nil {
		return nil, nil, err
	}
	defer func() { _ = f.Close() }()
	content, err := io.ReadAll(io.LimitReader(f, 65537))
	if err != nil {
		return nil, nil, err
	}
	*remaining -= len(content)
	if len(content) > 65536 || *remaining < 0 || contentDigest(content) != p.DeclarationsSHA256 {
		return nil, nil, fmt.Errorf("ARCH-015 %s: consumer declaration is too large or its content commitment is stale", name)
	}
	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, name, content, parser.AllErrors)
	if err != nil {
		return nil, nil, err
	}
	if file.Name.Name != path.Base(p.Path) {
		return nil, nil, fmt.Errorf("ARCH-015 %s: consumer package name does not match its path", name)
	}
	if err := checkConsumerBodies(file, name); err != nil {
		return nil, nil, err
	}
	return file, fset, nil
}

func (c *consumerTypes) checkImports(p ConsumerPackage, file *ast.File) error {
	for _, spec := range file.Imports {
		name, err := strconv.Unquote(spec.Path.Value)
		if err != nil {
			return err
		}
		for _, target := range c.model.ConsumerAPI.Packages {
			if c.model.consumerImport(target) == name && !slices.Contains(p.Uses, target.Owner+":"+target.Path) {
				return fmt.Errorf("ARCH-015 %s: consumer declaration import %s is absent from uses", p.Path, name)
			}
		}
	}
	return nil
}

func (c *consumerTypes) normalizeAPI(api []string) []string {
	normalized := make([]string, 0, len(api))
	for _, line := range api {
		for name, existing := range c.existing {
			line = strings.ReplaceAll(line, existing.Path(), name)
		}
		for _, planned := range c.model.ConsumerAPI.Packages {
			for _, module := range c.model.Modules {
				old := module.Path + "/" + planned.Path
				line = strings.ReplaceAll(line, old, c.model.consumerImport(planned))
			}
		}
		normalized = append(normalized, line)
	}
	slices.Sort(normalized)
	return normalized
}

func (c *consumerTypes) checkImplementedContracts() error {
	for _, planned := range c.model.ConsumerAPI.Packages {
		if err := c.checkImplementedContract(planned); err != nil {
			return err
		}
	}
	return nil
}

// checkImplementedContract compares the implemented code of one planned package
// with its declarations. An existing package compares only its implemented extensions.
func (c *consumerTypes) checkImplementedContract(planned ConsumerPackage) error {
	if planned.Declarations == "" {
		return nil
	}
	if planned.Existing != "" {
		actual, _ := c.model.pkg(planned.Existing)
		return c.checkExtensions(planned, actual)
	}
	for _, module := range c.model.Modules {
		actual, ok := c.model.pkg(module.Dir + "/" + planned.Path)
		if !ok {
			continue
		}
		intended := c.normalizeAPI(typeAPI(c.checked[c.model.consumerImport(planned)]))
		if err := c.checkConsumerSnapshots(actual, intended); err != nil {
			return err
		}
	}
	return nil
}

func (c *consumerTypes) checkConsumerSnapshots(actual Package, intended []string) error {
	for _, snapshot := range actual.API {
		normalized := c.normalizeAPI(snapshot)
		for _, declaration := range intended {
			if !slices.Contains(normalized, declaration) {
				return fmt.Errorf("ARCH-015 %s: implemented API differs from its typed consumer contract", actual.Dir)
			}
		}
	}
	return nil
}

func checkConsumerBodies(file *ast.File, name string) error {
	for _, decl := range file.Decls {
		if block, ok := decl.(*ast.GenDecl); ok && block.Tok == token.VAR {
			for _, spec := range block.Specs {
				value, ok := spec.(*ast.ValueSpec)
				if ok && len(value.Values) > 0 {
					return fmt.Errorf("ARCH-015 %s: planned consumer declarations cannot initialize variables", name)
				}
			}
		}
		if fn, ok := decl.(*ast.FuncDecl); ok && fn.Body != nil {
			return fmt.Errorf("ARCH-015 %s: planned consumer declarations cannot implement function bodies", name)
		}
	}
	return nil
}

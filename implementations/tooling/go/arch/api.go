package arch

import (
	"context"
	"fmt"
	"go/types"
	"io/fs"
	"maps"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"

	"golang.org/x/tools/go/packages"
)

// Configuration names one supported build context. IDs are stable model keys.
type Configuration struct {
	ID     string   `json:"id"`
	GOOS   string   `json:"goos"`
	GOARCH string   `json:"goarch"`
	Tags   []string `json:"tags"`
}

// API maps a package directory and build configuration to its typed surface.
type API map[string]map[string][]string

// LoadAPI loads production types without executing proposed code or resolving
// dependencies over the network. It rejects uncovered production source files.
func LoadAPI(ctx context.Context, root string, model *Model) (API, error) {
	if err := validateAPITree(root, model); err != nil {
		return nil, err
	}
	result := API{}
	covered := map[string]bool{}
	for _, module := range model.Modules {
		for _, config := range model.Configurations {
			if err := loadModuleAPI(ctx, root, model, module, config, result, covered); err != nil {
				return nil, err
			}
		}
	}
	if err := checkAPICoverage(root, model, covered); err != nil {
		return nil, err
	}
	return result, nil
}

func checkAPICoverage(root string, model *Model, covered map[string]bool) error {
	rooted, err := os.OpenRoot(root)
	if err != nil {
		return err
	}
	defer func() { _ = rooted.Close() }()
	for _, pkg := range model.Packages {
		entries, err := fs.ReadDir(rooted.FS(), pkg.Dir)
		if err != nil {
			return err
		}
		for _, entry := range entries {
			name := entry.Name()
			if strings.HasSuffix(name, ".go") && !strings.HasSuffix(name, "_test.go") && !strings.HasPrefix(name, "_") && !strings.HasPrefix(name, ".") && !covered[filepath.Join(root, pkg.Dir, name)] {
				return fmt.Errorf("%s/%s: production source is not covered by a declared API configuration; add its platform or build tags", pkg.Dir, name)
			}
		}
	}
	return nil
}

// CheckAPI compares typed code to the intended package interfaces.
func (m *Model) CheckAPI(actual API) []Finding {
	var findings []Finding
	for _, pkg := range m.Packages {
		if !maps.EqualFunc(pkg.API, actual[pkg.Dir], slices.Equal[[]string]) {
			findings = append(findings, Finding{Rule: ruleAPI, Location: pkg.Dir, Problem: "the exported API differs from its design.", Fix: "review the API and update its intended snapshot and owning design commitment."})
		}
	}
	return findings
}

func typeAPI(pkg *types.Package) []string {
	v := apiVisitor{seen: map[types.Type]bool{}, output: []string{"package " + pkg.Name()}}
	for _, name := range pkg.Scope().Names() {
		if object := pkg.Scope().Lookup(name); object.Exported() {
			v.object(object)
		}
	}
	return sortedUnique(v.output)
}

// objectAPI returns the typed surface of one package-level object.
func objectAPI(object types.Object) []string {
	v := apiVisitor{seen: map[types.Type]bool{}}
	v.object(object)
	return sortedUnique(v.output)
}

func (v *apiVisitor) object(object types.Object) {
	if _, isType := object.(*types.TypeName); !isType {
		declaration := types.ObjectString(object, apiQualifier)
		if constant, ok := object.(*types.Const); ok {
			declaration += " = " + constant.Val().ExactString()
		}
		v.output = append(v.output, declaration)
	}
	v.visit(object.Type())
}

type apiVisitor struct {
	seen   map[types.Type]bool
	output []string
}

func apiQualifier(p *types.Package) string { return p.Path() }
func typeText(t types.Type) string         { return types.TypeString(t, apiQualifier) }

func (v *apiVisitor) named(t *types.Named) {
	var constraints []string
	for p := range t.TypeParams().TypeParams() {
		constraints = append(constraints, p.Obj().Name()+" "+typeText(p.Constraint()))
		v.visit(p.Constraint())
	}
	underlying := t.Underlying()
	shape := typeText(underlying)
	if st, ok := underlying.(*types.Struct); ok {
		shape = v.structure(st)
	} else {
		v.visit(underlying)
	}
	v.output = append(v.output, "type "+typeText(t)+" constraints["+strings.Join(constraints, ", ")+"] "+shape+fmt.Sprintf(" comparable=%t", types.Comparable(t)))
	for _, receiver := range []types.Type{t, types.NewPointer(t)} {
		for selection := range types.NewMethodSet(receiver).Methods() {
			method := selection.Obj()
			if method.Exported() {
				v.output = append(v.output, "method "+typeText(receiver)+" "+types.ObjectString(method, apiQualifier)+" selected="+typeText(selection.Type()))
				v.visit(method.Type())
			}
		}
	}
}

func (v *apiVisitor) structure(st *types.Struct) string {
	var fields []string
	private := false
	for i := range st.NumFields() {
		field := st.Field(i)
		if !field.Exported() {
			private = true
		}
		if field.Exported() || field.Embedded() {
			fields = append(fields, field.Name()+" "+typeText(field.Type())+" "+strconv.Quote(st.Tag(i))+fmt.Sprintf(" embedded=%t", field.Embedded()))
			v.visit(field.Type())
		}
	}
	return "struct{" + strings.Join(fields, "; ") + fmt.Sprintf("} unexported-fields=%t", private)
}

func (v *apiVisitor) visit(t types.Type) {
	if t == nil || v.seen[t] {
		return
	}
	v.seen[t] = true
	switch t := t.(type) {
	case *types.Named:
		v.named(t)
	case *types.Alias:
		v.output = append(v.output, types.ObjectString(t.Obj(), apiQualifier))
		v.visit(t.Rhs())
	case *types.Signature:
		v.signature(t)
	case *types.Tuple:
		for p := range t.Variables() {
			v.visit(p.Type())
		}
	case *types.Interface:
		for method := range t.Methods() {
			v.visit(method.Type())
		}
		for embedded := range t.EmbeddedTypes() {
			v.visit(embedded)
		}
	case *types.Struct:
		v.structure(t)
	default:
		v.container(t)
	}
}

func (v *apiVisitor) signature(t *types.Signature) {
	v.visit(t.Params())
	v.visit(t.Results())
	for p := range t.TypeParams().TypeParams() {
		v.visit(p.Constraint())
	}
}

func (v *apiVisitor) container(t types.Type) {
	switch t := t.(type) {
	case *types.Pointer:
		v.visit(t.Elem())
	case *types.Slice:
		v.visit(t.Elem())
	case *types.Array:
		v.visit(t.Elem())
	case *types.Map:
		v.visit(t.Key())
		v.visit(t.Elem())
	case *types.Chan:
		v.visit(t.Elem())
	case *types.TypeParam:
		v.visit(t.Constraint())
	case *types.Union:
		for term := range t.Terms() {
			v.visit(term.Type())
		}
	}
}

func loadModuleAPI(ctx context.Context, root string, model *Model, module Module, config Configuration, result API, covered map[string]bool) error {
	env := append(os.Environ(), "GOWORK=off", "GO111MODULE=on", "GOPROXY=off", "GOSUMDB=off", "GOTOOLCHAIN=local", "GOFLAGS=-mod=readonly", "GOPACKAGESDRIVER=off", "CGO_ENABLED=0", "GOOS="+config.GOOS, "GOARCH="+config.GOARCH)
	loaded, err := packages.Load(&packages.Config{Context: ctx, Dir: filepath.Join(root, module.Dir), Env: env, Mode: packages.LoadTypes, BuildFlags: []string{"-tags=" + strings.Join(config.Tags, ",")}}, "./...")
	if err != nil {
		return fmt.Errorf("load API %s: %w", config.ID, err)
	}
	for _, pkg := range loaded {
		if len(pkg.Errors) > 0 {
			return fmt.Errorf("load API %s %s: %w", config.ID, pkg.PkgPath, pkg.Errors[0])
		}
		dir, ok := model.dirOf(pkg.PkgPath)
		if !ok {
			return fmt.Errorf("API package outside model: %s", pkg.PkgPath)
		}
		if result[dir] == nil {
			result[dir] = map[string][]string{}
		}
		result[dir][config.ID] = typeAPI(pkg.Types)
		for _, file := range pkg.GoFiles {
			covered[filepath.Clean(file)] = true
		}
	}
	return nil
}

func validateAPITree(root string, model *Model) error {
	rooted, err := os.OpenRoot(root)
	if err != nil {
		return err
	}
	defer func() { _ = rooted.Close() }()
	for _, pkg := range model.Packages {
		if _, err := rooted.Stat(pkg.Dir); err != nil {
			return fmt.Errorf("validate API package containment: %w", err)
		}
	}
	for _, module := range model.Modules {
		if !isRepoDir(module.Dir) {
			return fmt.Errorf("unsafe module directory %q", module.Dir)
		}
		err := fs.WalkDir(rooted.FS(), module.Dir, containedSource(rooted, module.Dir))
		if err != nil {
			return fmt.Errorf("validate API source containment: %w", err)
		}
	}
	return nil
}

func containedSource(rooted *os.Root, moduleDir string) fs.WalkDirFunc {
	return func(name string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if name != moduleDir && ignoredDir(entry.Name()) {
				return fs.SkipDir
			}
			return nil
		}
		if strings.HasSuffix(name, ".go") || entry.Name() == "go.mod" {
			file, err := rooted.Open(name)
			if err != nil {
				return err
			}
			return file.Close()
		}
		return nil
	}
}

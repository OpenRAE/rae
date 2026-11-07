package authoring

import (
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"path"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type composition struct {
	parser      *Parser
	request     Request
	supplied    *source.Sources
	budget      *source.Budget
	seen        map[string]bool
	localDenied map[string]bool
}

func (p *Parser) checkImports(document *Document, request Request, captured *source.Sources) error {
	value, err := p.modelValue(document)
	if err != nil {
		return err
	}
	if len(array(value["imports"])) == 0 {
		return nil
	}
	if request.Name == "" {
		return invalid()
	}
	c := composition{parser: p, request: request, seen: map[string]bool{}, localDenied: map[string]bool{}}
	c.budget, err = source.NewBudget(p.limits)
	if err != nil {
		return err
	}
	c.supplied = captured
	_, err = c.expand(document, value, request.Name, 0)
	return err
}
func (p *Parser) modelValue(document *Document) (map[string]any, error) {
	value, err := ingress.Parse(document.data, ingress.Limits{MaxBytes: int(p.limits.MaxComposedBytes), MaxDepth: p.limits.MaxDepth}, ingress.Object)
	if err != nil {
		return nil, err
	}
	return object(value), nil
}
func (c *composition) charge(document *Document) error {
	return c.budget.AddValue(document.compositionValue)
}
func (c *composition) expand(document *Document, value map[string]any, name string, depth int) (map[string]any, error) {
	if err := c.budget.CheckDepth(depth); err != nil {
		return nil, err
	}
	if err := c.charge(document); err != nil {
		return nil, err
	}
	if c.seen[name] {
		return nil, importError("cycle")
	}
	c.seen[name] = true
	defer delete(c.seen, name)
	imports := array(value["imports"])
	lock, err := c.lock(name, len(imports) > 0)
	if err != nil {
		return nil, err
	}
	if c.supplied == nil {
		if err = c.trust(name); err != nil {
			return nil, err
		}
	}
	for _, raw := range imports {
		if err = c.budget.AddImport(); err != nil {
			return nil, err
		}
		if err = c.edge(value, object(raw), name, depth, lock); err != nil {
			return nil, err
		}
	}
	delete(value, "imports")
	return value, nil
}
func (c *composition) edge(parent, decl map[string]any, importer string, depth int, lock *lockfile) error {
	decl, err := c.resolveLocked(decl, lock)
	if err != nil {
		return err
	}
	requested := importSource(decl)
	if err = c.budget.CheckDepth(depth + 1); err != nil {
		return err
	}
	if err = c.checkImportDecl(decl, requested); err != nil {
		return err
	}
	relative := strings.TrimPrefix(requested, "local:")
	name, err := c.localName(importer, relative)
	if err != nil {
		return err
	}
	raw, err := c.read(name)
	if err != nil {
		return err
	}
	child, err := c.parser.decode(raw, name, "reject")
	if err != nil {
		return err
	}
	value, err := c.parser.modelValue(child)
	if err != nil {
		return err
	}
	descriptor, err := admittedModule(child, value, decl, raw, c.localDenied[importer])
	if err != nil {
		return err
	}
	if err = c.checkLock(lock, decl, descriptor, raw, requested, relative); err != nil {
		return err
	}
	if value["semantic_revision"] != parent["semantic_revision"] {
		return importError("revision-mismatch")
	}
	expanded, err := c.expand(child, value, name, depth+1)
	if err != nil {
		return err
	}
	if err = validateExports(expanded, descriptor); err != nil {
		return err
	}
	expanded, err = c.bind(expanded, decl, descriptor)
	if err != nil {
		return err
	}
	return c.combine(parent, expanded, text(decl["namespace"]), descriptor)
}
func importSource(decl map[string]any) string {
	if requested := text(decl[sourceField]); requested != "" {
		return requested
	}
	return "local:" + text(decl["path"])
}
func (c *composition) checkImportDecl(decl map[string]any, requested string) error {
	if !strings.HasPrefix(requested, "local:") {
		return importError("source-refused")
	}
	namespace := text(decl["namespace"])
	if namespace == "" || namespace == privateSegment || strings.Contains(namespace, ".") {
		return importError("namespace-invalid")
	}
	if c.supplied != nil {
		pin := text(decl["digest"])
		if pin == "" {
			return importError("digest-missing")
		}
		if !strictPin(pin) {
			return importError("digest-invalid")
		}
	}
	return nil
}
func (c *composition) localName(importer, relative string) (string, error) {
	name, err := source.ResolvePath(path.Dir(importer), relative)
	if err != nil {
		return "", err
	}
	if c.supplied == nil && !withinDirectory(path.Dir(importer), name) {
		return "", importError("path-invalid")
	}
	return name, nil
}
func admittedModule(document *Document, value, decl map[string]any, raw []byte, localDenied bool) (map[string]any, error) {
	descriptor := object(value["module"])
	if document.contract != authoringContract || descriptor == nil {
		return nil, importError("descriptor-missing")
	}
	requirement, err := versionSpec(text(decl["version"]))
	if err != nil {
		return nil, err
	}
	if !requirement.accepts(text(descriptor["version"])) {
		return nil, importError("version-mismatch")
	}
	if localDenied {
		return nil, importError("local-disabled")
	}
	if !pinMatches(raw, text(decl["digest"])) {
		return nil, importError("digest-mismatch")
	}
	return descriptor, nil
}
func withinDirectory(directory, name string) bool {
	return directory == "." || strings.HasPrefix(name, directory+"/")
}
func (c *composition) read(name string) ([]byte, error) {
	if c.supplied != nil {
		return c.supplied.Bytes(name)
	}
	if c.request.FS == nil {
		return nil, importError("source-missing")
	}
	return c.readBounded(name, c.parser.limits.MaxInputBytes)
}
func (c *composition) readBounded(name string, limit int64) ([]byte, error) {
	file, err := c.request.FS.Open(name)
	if err != nil {
		return nil, importReadError(err)
	}
	defer func() { _ = file.Close() }()
	raw, err := io.ReadAll(io.LimitReader(file, limit))
	if err != nil {
		return nil, importReadError(err)
	}
	var extra [1]byte
	n, err := io.ReadFull(file, extra[:])
	if err != nil && !errors.Is(err, io.EOF) && !errors.Is(err, io.ErrUnexpectedEOF) {
		return nil, importReadError(err)
	}
	if n > 0 {
		return nil, importError("budget-exceeded")
	}
	return raw, nil
}
func importReadError(err error) error {
	if errors.Is(err, fs.ErrNotExist) {
		return importError("source-missing")
	}
	return &importParseError{code: "source-unreadable", category: fault.Operational, cause: err}
}
func importError(code string) error {
	return &importParseError{code: code, category: fault.InvalidInput}
}

type importParseError struct {
	code     string
	category fault.Category
	cause    error
}

func (e *importParseError) Error() string            { return "sdl import rejected" }
func (e *importParseError) Code() string             { return "sdl.import." + e.code }
func (e *importParseError) Category() fault.Category { return e.category }
func (e *importParseError) Unwrap() error            { return e.cause }
func toJSON(value any) ([]byte, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, invalid()
	}
	return raw, nil
}

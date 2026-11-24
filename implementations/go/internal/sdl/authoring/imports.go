package authoring

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"maps"
	"path"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
	"github.com/OpenRAE/rae/implementations/go/sdl/module"
)

type composition struct {
	parser       *Parser
	request      Request
	supplied     *source.Sources
	budget       *source.Budget
	copies       copyBudget
	modelBuffers *copyBudget
	seen         map[string]bool
	localDenied  map[string]bool
	records      map[string][]map[string]any
	facts        map[string]*importFacts
	snapshot     map[string][]byte
	verified     map[string]*verifiedSources
	remoteFacts  map[string]module.LockRecord
}

func (p *Parser) checkImports(ctx context.Context, document *Document, request Request, captured *source.Sources) error {
	if captured != nil && document.contract != authoringContract {
		return importError("phase-refused")
	}
	value, err := p.modelValue(document)
	if err != nil {
		return err
	}
	if len(array(value[importsField])) == 0 {
		return nil
	}
	if request.Name == "" {
		return invalid()
	}
	c := composition{parser: p, request: request, seen: map[string]bool{}, localDenied: map[string]bool{}, records: map[string][]map[string]any{}}
	c.budget, err = source.NewBudget(p.limits)
	if err != nil {
		return err
	}
	c.copies.remaining = p.limits.MaxComposedBytes
	c.supplied = captured
	name := request.Name
	if captured == nil {
		name, err = c.fileName(name)
		if err != nil {
			return err
		}
	}
	expanded, err := c.expand(ctx, document, value, name, 0)
	if err != nil {
		return err
	}
	return c.retainExpanded(document, expanded, name)
}
func (p *Parser) modelValue(document *Document) (map[string]any, error) {
	data := document.modelBytes()
	value, err := ingress.Parse(data, modelLimits(data), ingress.Object)
	if err != nil {
		return nil, err
	}
	return object(value), nil
}
func (c *composition) charge(document *Document) error {
	return c.budget.AddValue(document.compositionValue)
}
func (c *composition) expand(ctx context.Context, document *Document, value map[string]any, name string, depth int) (map[string]any, error) {
	if err := ctx.Err(); err != nil {
		return nil, fault.New(fault.Operational, "sdl-operation-canceled", err)
	}
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
	c.records[name] = nil
	if c.facts == nil {
		c.facts = map[string]*importFacts{}
	}
	facts, err := newImportFacts(document, value)
	if err != nil {
		return nil, err
	}
	c.facts[name] = facts
	if _, present := value["version"]; !present {
		value["version"] = "*"
	}
	if err = c.expandImports(ctx, value, name, depth); err != nil {
		return nil, err
	}
	delete(value, importsField)
	return value, nil
}
func (c *composition) expandImports(ctx context.Context, value map[string]any, name string, depth int) error {
	imports := array(value[importsField])
	lock, err := c.lock(name, len(imports) > 0)
	if err != nil {
		return err
	}
	if c.supplied == nil {
		if err = c.trust(name); err != nil {
			return err
		}
	}
	for _, raw := range imports {
		if err = c.budget.AddImport(); err != nil {
			return err
		}
		if err = c.edge(ctx, value, object(raw), name, depth, lock); err != nil {
			return err
		}
	}
	return nil
}
func (c *composition) edge(ctx context.Context, parent, decl map[string]any, importer string, depth int, lock *lockfile) error {
	requestedDecl := decl
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
	name, raw, remote, err := c.importBytes(ctx, decl, requested, importer, lock)
	if err != nil {
		return err
	}
	child, value, err := c.importDocument(raw, name)
	if err != nil {
		return err
	}
	descriptor, err := admittedModule(child, value, resolvedImportDeclaration(decl, remote), raw, !remote && c.localDenied[importer])
	if err != nil {
		return err
	}
	if !remote {
		err = c.checkLock(lock, decl, descriptor, raw, requested, relativeSource(path.Dir(importer), name))
	}
	if err != nil {
		return err
	}
	if value["semantic_revision"] != parent["semantic_revision"] {
		return importError("revision-mismatch")
	}
	expanded, err := c.expand(ctx, child, value, name, depth+1)
	if err != nil {
		return err
	}
	if err = validateExports(expanded, descriptor); err != nil {
		return err
	}
	if err = c.admitLocalTrust(ctx, importer, decl, descriptor, raw, remote); err != nil {
		return err
	}
	expanded, err = c.bind(expanded, decl, descriptor, c.facts[name])
	if err != nil {
		return err
	}
	symbols := symbolsFor(expanded, text(decl[namespaceField]), descriptor)
	if err = c.combine(parent, expanded, text(decl[namespaceField]), descriptor); err != nil {
		return err
	}
	c.inheritImportFacts(importer, name, text(decl[namespaceField]), symbols)
	return c.addImportRecords(importer, name, requestedDecl, descriptor, raw)
}

func resolvedImportDeclaration(decl map[string]any, remote bool) map[string]any {
	if !remote {
		return decl
	}
	// Registry admission already checked the bundle content identity. Its pin
	// must not be compared with the different bytes of the root source file.
	result := maps.Clone(decl)
	delete(result, "digest")
	return result
}

func (c *composition) importDocument(raw []byte, name string) (*Document, map[string]any, error) {
	child, err := c.parser.decodeDocument(raw, name, "reject", true)
	if err != nil {
		return nil, nil, err
	}
	value, err := c.parser.modelValue(child)
	if err != nil {
		return nil, nil, err
	}
	if err = c.parser.checkModuleEffectTargets(child); err != nil {
		return nil, nil, err
	}
	return child, value, nil
}
func importSource(decl map[string]any) string {
	if requested := text(decl[sourceField]); requested != "" {
		return requested
	}
	return localImportPrefix + text(decl["path"])
}
func (c *composition) checkImportDecl(decl map[string]any, requested string) error {
	if !strings.HasPrefix(requested, localImportPrefix) && (c.supplied != nil || c.request.Registry == nil || !strings.HasPrefix(requested, "oci:")) {
		return importError("source-refused")
	}
	namespace := text(decl[namespaceField])
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
	directory := path.Dir(importer)
	if scope, logical := c.verifiedScope(importer); scope != nil {
		name, err := scope.sources.Resolve(path.Dir(logical), relative)
		if err != nil {
			return "", err
		}
		return scope.root + "/" + name, nil
	}
	if c.supplied != nil {
		return c.supplied.Resolve(directory, relative)
	}
	name := relative
	if !path.IsAbs(relative) {
		name = directory + "/" + relative
	}
	resolved, err := c.fileName(name)
	if err != nil {
		return "", err
	}
	if !withinDirectory(directory, resolved) {
		return "", importError(pathInvalidCode)
	}
	return resolved, nil
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
	if !requirement.Accepts(text(descriptor["version"])) {
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
	if scope, logical := c.verifiedScope(name); scope != nil {
		return scope.sources.Bytes(logical)
	}
	if c.supplied != nil {
		return c.supplied.Bytes(name)
	}
	if c.request.FS == nil {
		return nil, importError("source-missing")
	}
	raw, err := c.readBounded(name, c.parser.limits.MaxInputBytes)
	if err == nil && c.snapshot != nil {
		c.snapshot[name] = raw
	}
	return raw, err
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
		return nil, importError(budgetExceededCode)
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

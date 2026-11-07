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
	parser   *Parser
	request  Request
	supplied *source.Sources
	budget   *source.Budget
	seen     map[string]bool
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
	c := composition{parser: p, request: request, seen: map[string]bool{}}
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
	options := c.parser.options("", "reject")
	options.KeyScope = "data"
	options.Limits.MaxInputBytes = c.parser.limits.MaxComposedBytes
	options.Limits.MaxNodes = c.parser.limits.MaxComposedNodes
	options.Limits.MaxExpandedNodes = c.parser.limits.MaxComposedNodes
	normalized, err := source.Decode(document.data, options)
	if err != nil {
		return err
	}
	return c.budget.AddDocument(normalized)
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
		if err = c.trust(name, len(imports) > 0); err != nil {
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
	requested := text(decl["source"])
	if requested == "" {
		requested = "local:" + text(decl["path"])
	}
	if !strings.HasPrefix(requested, "local:") {
		return importError("source-refused")
	}
	relative := strings.TrimPrefix(requested, "local:")
	namespace := text(decl["namespace"])
	if namespace == "" || namespace == "__private" || strings.Contains(namespace, ".") {
		return importError("namespace-invalid")
	}
	pin := text(decl["digest"])
	if c.supplied != nil {
		if pin == "" {
			return importError("digest-missing")
		}
		if !strictPin(pin) {
			return importError("digest-invalid")
		}
	}
	name, err := source.ResolvePath(path.Dir(importer), relative)
	if err != nil {
		return err
	}
	if c.supplied == nil && !withinDirectory(path.Dir(importer), name) {
		return importError("path-invalid")
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
	if child.contract != "sdl-authoring-input-v1" {
		return importError("descriptor-missing")
	}
	descriptor := object(value["module"])
	if descriptor == nil {
		return importError("descriptor-missing")
	}
	requirement, err := versionSpec(text(decl["version"]))
	if err != nil {
		return err
	}
	if !requirement.accepts(text(descriptor["version"])) {
		return importError("version-mismatch")
	}
	if !pinMatches(raw, pin) {
		return importError("digest-mismatch")
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
	return c.combine(parent, expanded, namespace, descriptor)
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
	file, err := c.request.FS.Open(name)
	if err != nil {
		return nil, importReadError(err)
	}
	defer func() { _ = file.Close() }()
	raw, err := io.ReadAll(io.LimitReader(file, c.parser.limits.MaxInputBytes))
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

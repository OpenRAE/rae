// Package authoring owns structural SDL normalization and canonical formatting.
// A structural document does not grant semantic or execution authority.
package authoring

import (
	"bytes"
	"embed"
	"encoding/json"
	"io/fs"
	"maps"
	"path"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/concept"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// The embedded presentation metadata is immutable and has no validation authority.
//
//go:embed layout.json
var presentation embed.FS

// Request supplies source bytes and an explicit import authority. A source map
// selects isolated supplied-source admission; it never falls back to FS.
type Request struct {
	Source []byte
	Name   string
	// RootDir identifies the canonical absolute directory represented by FS.
	// It grants no read authority and is ignored when Sources is supplied.
	RootDir string
	FS      fs.FS
	Sources map[string][]byte
}

// Result contains strict authored YAML and migration advisories.
type Result struct {
	Content     []byte
	Diagnostics []source.Diagnostic
}

// Parser holds immutable schemas, presentation metadata and input ceilings.
// It is safe for concurrent requests; composition state is request-local.
type Parser struct {
	evidenceContracts map[string]bool
	limits            source.Limits
	models            *admission.Validator
	authority         *concept.Authority
	schemas           map[string]map[string]any
	layouts           map[string]map[string]layout
}

type layout struct {
	Fields          []string                   `json:"fields"`
	Omit            map[string][]string        `json:"omit"`
	Scalar          map[string]scalarPolicy    `json:"scalar"`
	FactoryDefaults map[string]json.RawMessage `json:"factory_defaults"`
}

// New loads the packaged contracts and checks presentation metadata against them.
func New(limits source.Limits) (*Parser, error) {
	if err := limits.Validate(); err != nil {
		return nil, err
	}
	compiled, err := validation.New(nil)
	if err != nil {
		return nil, err
	}
	models, err := admission.NewWithSchemas(compiled)
	if err != nil {
		return nil, err
	}
	authority, err := concept.Load(compiled)
	if err != nil {
		return nil, err
	}
	packaged, err := corpus.Open()
	if err != nil {
		return nil, err
	}
	p := &Parser{limits: limits, models: models, authority: authority, schemas: map[string]map[string]any{}}
	p.evidenceContracts, err = manifestEvidenceContracts(packaged)
	if err != nil {
		return nil, err
	}
	raw, err := presentation.ReadFile("layout.json")
	if err != nil {
		return nil, err
	}
	if err = json.Unmarshal(raw, &p.layouts); err != nil {
		return nil, err
	}
	for _, id := range []string{authoringContract, materializedContract} {
		raw, err = fs.ReadFile(packaged, "schemas/sdl/"+id+".json")
		if err != nil {
			return nil, err
		}
		var schema map[string]any
		if err = json.Unmarshal(raw, &schema); err != nil {
			return nil, err
		}
		p.schemas[id] = schema
		if err = p.checkLayout(id); err != nil {
			return nil, err
		}
	}
	return p, nil
}
func (p *Parser) checkLayout(id string) error {
	for pointer, l := range p.layoutRecords(id) {
		schema := resolve(p.schemas[id], pointer)
		props := object(schema["properties"])
		for _, name := range l.Fields {
			if _, ok := props[name]; !ok {
				return fault.New(fault.Operational, "sdl-presentation-contract", nil)
			}
		}
		for name, raw := range l.FactoryDefaults {
			if _, present := props[name]; !present || len(raw) > 16384 || !json.Valid(raw) {
				return fault.New(fault.Operational, "sdl-presentation-contract", nil)
			}
		}
	}
	return nil
}

// Document is an immutable structurally checked authored or materialized model.
// Each accessor returns a fresh copy. Semantic admission is a later operation.
type Document struct {
	contract         string
	data             []byte
	source           *source.Document
	compositionValue map[string]any
	warnings         []source.Diagnostic
}

// JSON copies the normalized, supplied-field representation.
func (d *Document) JSON() []byte { return slices.Clone(d.data) }

// Decode checks strict source and the structural model, including imports.
func (p *Parser) Decode(request Request) (*Document, error) {
	captured, err := captureRequest(request)
	if err != nil {
		return nil, err
	}
	document, err := p.decode(request.Source, request.Name, "reject")
	if err != nil {
		return nil, err
	}
	if err = p.checkImports(document, request, captured); err != nil {
		return nil, err
	}
	return document, nil
}

// Format migrates supported syntax, emits model field order, and strictly
// re-admits the resulting source and import graph before returning bytes.
func (p *Parser) Format(request Request) (Result, error) {
	captured, err := captureRequest(request)
	if err != nil {
		return Result{}, err
	}
	d, err := p.decode(request.Source, request.Name, "accept")
	if err != nil {
		return Result{}, err
	}
	options := p.options(request.Name, "reject")
	options.KeyScope = dataScope
	options.BasePointer = "/formatted_model"
	options.Limits.MaxInputBytes = int64(len(d.data))
	options.Limits.MaxScalarBytes = int64(len(d.data))
	options.Limits.MaxNodes = len(d.data)
	options.Limits.MaxExpandedNodes = len(d.data)
	options.Limits.MaxDepth = len(d.data)
	ordered, err := source.Decode(d.data, options)
	if err != nil {
		return Result{}, err
	}
	content, err := ordered.Render(p.limits.MaxInputBytes)
	if err != nil {
		return Result{}, err
	}
	request.Source = content
	strict, err := p.decode(request.Source, request.Name, "reject")
	if err != nil {
		return Result{}, err
	}
	if err = p.checkImports(strict, request, captured); err != nil {
		return Result{}, err
	}
	if err = p.checkFormatPhase(strict); err != nil {
		return Result{}, err
	}
	return Result{Content: content, Diagnostics: d.warnings}, nil
}
func (p *Parser) options(name, policy string) source.Options {
	options := source.DefaultOptions()
	options.Limits = p.limits
	options.Name = name
	options.RequireMapping = true
	options.MigrationPolicy = policy
	return options
}
func (p *Parser) decode(raw []byte, name, policy string) (*Document, error) {
	return p.decodeDocument(raw, name, policy, false)
}
func (p *Parser) decodeDocument(raw []byte, name, policy string, imported bool) (*Document, error) {
	parsed, err := source.Decode(raw, p.options(name, policy))
	if err != nil {
		return nil, err
	}
	if revision, present := object(parsed.Value())["semantic_revision"]; present && revision != "raes-progressive-semantics/v1" {
		return nil, invalid()
	}
	value := object(parsed.NormalizedValue())
	hints := map[string][]string{}
	if err = shorthands(value, hints); err != nil {
		return nil, err
	}
	migrated, err := migrateVM(value, parsed, policy, name)
	if err != nil {
		return nil, err
	}

	id := authoringContract
	if _, present := value["materialization_provenance"]; present {
		id = materializedContract
	}
	if id == authoringContract {
		if err = authoredReferences(value, nil); err != nil {
			return nil, err
		}
	}
	if containsVariable(value[controlAssetsSection]) {
		return nil, invalid()
	}
	if err = p.precheckComposition(value, imported); err != nil {
		return nil, err
	}
	encoded, err := p.construct(value, id, hints, parsed)
	if err != nil {
		return nil, err
	}
	warnings := append(parsed.Diagnostics(), migrated...)
	return &Document{compositionValue: value, contract: id, data: encoded, source: parsed, warnings: warnings}, nil
}
func (p *Parser) precheckComposition(value map[string]any, imported bool) error {
	if !imported && len(array(value["imports"])) == 0 {
		return nil
	}
	budget, err := source.NewBudget(p.limits)
	if err != nil {
		return err
	}
	return budget.AddValue(value)
}
func (p *Parser) construct(value map[string]any, id string, hints map[string][]string, parsed *source.Document) ([]byte, error) {
	limit := jsonWorkingLimit(p.limits.MaxInputBytes, p.limits.MaxExpandedNodes)
	walk := normalizer{parser: p, id: id, hints: hints, workingLimit: limit}
	normalized, err := walk.walk(p.schemas[id], "#", value, nil, scalarPolicy{}, parsed.View())
	if err != nil {
		return nil, err
	}
	encoded, err := encode(normalized, limit, false)
	if err != nil {
		return nil, err
	}
	if err = p.models.CheckSDLConstruction(id, "#", encoded, modelLimits(encoded)); err != nil {
		return nil, &modelError{path: "", cause: err}
	}
	return encode(normalized, limit, true)
}
func invalid() error { return fault.New(fault.InvalidInput, "sdl-model-invalid", nil) }
func object(value any) map[string]any {
	switch v := value.(type) {
	case map[string]any:
		return v
	case ordered:
		result := make(map[string]any, len(v))
		for _, field := range v {
			result[field.name] = field.value
		}
		return result
	default:
		return nil
	}
}
func array(v any) []any { s, _ := v.([]any); return s }
func text(v any) string { s, _ := v.(string); return s }

// captureRequest returns no captured authority when the caller selected FS.
//
//nolint:nilnil // A nil capture distinguishes filesystem authority from supplied sources.
func captureRequest(request Request) (*source.Sources, error) {
	if err := requestPaths(request); err != nil {
		return nil, err
	}
	if request.Sources != nil {
		captured, err := source.Capture(request.Sources)
		if err != nil {
			return nil, err
		}
		root, err := captured.Bytes(request.Name)
		if err != nil {
			return nil, err
		}
		if !bytes.Equal(root, request.Source) {
			return nil, importError("source-refused")
		}
		return captured, nil
	}
	return nil, nil
}

func requestPaths(request Request) error {
	if request.FS != nil || request.Sources != nil {
		if request.Name == "." || !fs.ValidPath(request.Name) {
			return importError(pathInvalidCode)
		}
	}
	if request.Sources == nil && request.RootDir != "" {
		if !path.IsAbs(request.RootDir) || path.Clean(request.RootDir) != request.RootDir || strings.ContainsRune(request.RootDir, 0) {
			return importError(pathInvalidCode)
		}
	}
	return nil
}

func (p *Parser) layoutRecords(id string) map[string]layout {
	result := make(map[string]layout, len(p.layouts[sharedLayoutKey])+len(p.layouts[id]))
	maps.Copy(result, p.layouts[sharedLayoutKey])
	maps.Copy(result, p.layouts[id])
	return result
}
func (p *Parser) layoutFor(id, pointer string) layout {
	if row, present := p.layouts[id][pointer]; present {
		return row
	}
	return p.layouts[sharedLayoutKey][pointer]
}

// Internal model bytes have already passed source or composition accounting.
// They are not a new untrusted source and do not consume those budgets again.
func modelLimits(data []byte) ingress.Limits {
	return ingress.Limits{MaxBytes: len(data)}
}

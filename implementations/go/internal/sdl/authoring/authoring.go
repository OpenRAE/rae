// Package authoring owns structural SDL normalization and canonical formatting.
// A structural document does not grant semantic or execution authority.
package authoring

import (
	"bytes"
	"embed"
	"encoding/json"
	"io/fs"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
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
	Source  []byte
	Name    string
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
	limits  source.Limits
	models  *admission.Validator
	schemas map[string]map[string]any
	layouts map[string]map[string]layout
}

type layout struct {
	Fields []string            `json:"fields"`
	Omit   map[string][]string `json:"omit"`
}

// New loads the packaged contracts and checks presentation metadata against them.
func New(limits source.Limits) (*Parser, error) {
	if err := limits.Validate(); err != nil {
		return nil, err
	}
	models, err := admission.New()
	if err != nil {
		return nil, err
	}
	packaged, err := corpus.Open()
	if err != nil {
		return nil, err
	}
	p := &Parser{limits: limits, models: models, schemas: map[string]map[string]any{}}
	raw, err := presentation.ReadFile("layout.json")
	if err != nil {
		return nil, err
	}
	if err = json.Unmarshal(raw, &p.layouts); err != nil {
		return nil, err
	}
	for _, id := range []string{"sdl-authoring-input-v1", "materialized-scenario-v1"} {
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
	for pointer, l := range p.layouts[id] {
		schema := resolve(p.schemas[id], pointer)
		props := object(schema["properties"])
		for _, name := range l.Fields {
			if _, ok := props[name]; !ok {
				return fault.New(fault.Operational, "sdl-presentation-contract", nil)
			}
		}
	}
	return nil
}

// Document is an immutable structurally checked authored or materialized model.
// Each accessor returns a fresh copy. Semantic admission is a later operation.
type Document struct {
	contract string
	data     []byte
	source   *source.Document
	warnings []source.Diagnostic
}

// JSON copies the normalized, supplied-field representation.
func (d *Document) JSON() []byte { return slices.Clone(d.data) }

// Authored returns a fresh typed authored binding when the document is authored.
func (d *Document) Authored() (binding.SdlAuthoringInputV1, bool) {
	var result binding.SdlAuthoringInputV1
	if d.contract != "sdl-authoring-input-v1" {
		return result, false
	}
	return result, json.Unmarshal(d.data, &result) == nil
}

// Materialized returns a fresh typed materialized binding when appropriate.
func (d *Document) Materialized() (binding.MaterializedScenarioV1, bool) {
	var result binding.MaterializedScenarioV1
	if d.contract != "materialized-scenario-v1" {
		return result, false
	}
	return result, json.Unmarshal(d.data, &result) == nil
}

// Decode checks strict source and the structural model, including imports.
func (p *Parser) Decode(request Request) (*Document, error) {
	document, err := p.decode(request.Source, request.Name, "reject")
	if err != nil {
		return nil, err
	}
	if err = p.checkImports(document, request); err != nil {
		return nil, err
	}
	return document, nil
}

// Format migrates supported syntax, emits model field order, and strictly
// re-admits the resulting source and import graph before returning bytes.
func (p *Parser) Format(request Request) (Result, error) {
	d, err := p.decode(request.Source, request.Name, "accept")
	if err != nil {
		return Result{}, err
	}
	options := p.options(request.Name, "reject")
	options.KeyScope = "data"
	options.Limits.MaxInputBytes = p.limits.MaxComposedBytes
	options.Limits.MaxScalarBytes = p.limits.MaxComposedBytes
	options.Limits.MaxNodes = p.limits.MaxComposedNodes
	options.Limits.MaxExpandedNodes = p.limits.MaxComposedNodes
	ordered, err := source.Decode(d.data, options)
	if err != nil {
		return Result{}, err
	}
	content, err := ordered.Render(p.limits.MaxInputBytes)
	if err != nil {
		return Result{}, err
	}
	request.Source = content
	if _, err = p.Decode(request); err != nil {
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
	parsed, err := source.Decode(raw, p.options(name, policy))
	if err != nil {
		return nil, err
	}
	value := object(parsed.NormalizedValue())
	if revision, present := value["semantic_revision"]; present && revision != "raes-progressive-semantics/v1" {
		return nil, invalid()
	}
	warnings := parsed.Diagnostics()
	if err = shorthands(value); err != nil {
		return nil, err
	}
	migrated, err := migrateVM(value, parsed, policy, name)
	if err != nil {
		return nil, err
	}
	warnings = append(warnings, migrated...)
	id := "sdl-authoring-input-v1"
	if _, present := value["materialization_provenance"]; present {
		id = "materialized-scenario-v1"
	}
	walk := normalizer{parser: p, id: id, ranges: parsed.KeyRanges(), remaining: p.limits.MaxComposedNodes}
	normalized, err := walk.walk(p.schemas[id], "#", value, "")
	if err != nil {
		return nil, err
	}
	encoded, err := encode(normalized, p.limits.MaxComposedBytes)
	if err != nil {
		return nil, err
	}
	limits := ingress.Limits{MaxBytes: int(p.limits.MaxComposedBytes), MaxDepth: p.limits.MaxDepth}
	if err = p.models.CheckPortable(id, encoded, limits); err != nil {
		return nil, &modelError{path: "", cause: err}
	}
	return &Document{contract: id, data: encoded, source: parsed, warnings: warnings}, nil
}
func invalid() error              { return fault.New(fault.InvalidInput, "sdl-model-invalid", nil) }
func object(v any) map[string]any { m, _ := v.(map[string]any); return m }
func array(v any) []any           { s, _ := v.([]any); return s }
func text(v any) string           { s, _ := v.(string); return s }

// encode uses an ordered object representation and stops before exceeding its ceiling.
func encode(value any, limit int64) ([]byte, error) {
	var out bytes.Buffer
	if err := writeJSON(&out, value, limit); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

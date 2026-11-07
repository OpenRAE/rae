// Package source decodes bounded SDL YAML without granting scenario admission.
// It keeps ordered keys until the source preflight has checked every collision.
package source

import (
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"maps"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// Limits bound source work and the complete composition request.
type Limits struct {
	MaxInputBytes       int64 `json:"max_input_bytes"`
	MaxScalarBytes      int64 `json:"max_scalar_bytes"`
	MaxComposedBytes    int64 `json:"max_composed_bytes"`
	MaxDepth            int   `json:"max_depth"`
	MaxNodes            int   `json:"max_nodes"`
	MaxAliases          int   `json:"max_aliases"`
	MaxExpandedNodes    int   `json:"max_expanded_nodes"`
	MaxImports          int   `json:"max_imports"`
	MaxComposedNodes    int   `json:"max_composed_nodes"`
	MaxCompositionDepth int   `json:"max_composition_depth"`
	MaxNamespaceDepth   int   `json:"max_namespace_depth"`
}

// DefaultLimits returns the sdl-yaml/v1 limits.
func DefaultLimits() Limits {
	return Limits{MaxInputBytes: 8 * 1024 * 1024, MaxScalarBytes: 1024 * 1024, MaxComposedBytes: 32 * 1024 * 1024,
		MaxDepth: 128, MaxNodes: 100000, MaxAliases: 256, MaxExpandedNodes: 250000, MaxImports: 256,
		MaxComposedNodes: 500000, MaxCompositionDepth: 32, MaxNamespaceDepth: 32}
}

// Validate refuses a nonpositive limit before processing input.
func (l Limits) Validate() error {
	for _, n := range []int64{l.MaxInputBytes, l.MaxScalarBytes, l.MaxComposedBytes, int64(l.MaxDepth), int64(l.MaxNodes), int64(l.MaxAliases), int64(l.MaxExpandedNodes), int64(l.MaxImports), int64(l.MaxComposedNodes), int64(l.MaxCompositionDepth), int64(l.MaxNamespaceDepth)} {
		if n < 1 {
			return fault.New(fault.InvalidInput, "sdl-limit-definition", nil)
		}
	}
	return nil
}

// Options select the source policy. Use DefaultOptions, then change explicit fields.
// KeyScope is structural, literal or data. Name is a diagnostic identity only.
// RequireMapping selects a document rather than a fragment.
type Options struct {
	Limits           Limits
	SourceFormat     string
	MigrationPolicy  string
	KeyScope         string
	BasePointer      string
	Name             string
	RequiredRevision string
	RequireMapping   bool
}

// DefaultOptions selects strict structural sdl-yaml/v1 decoding.
func DefaultOptions() Options {
	return Options{Limits: DefaultLimits(), SourceFormat: "sdl-yaml/v1", MigrationPolicy: "reject", KeyScope: structuralScope}
}

// Position is a one-based Unicode code-point position.
type Position struct {
	Line   int `json:"line"`
	Column int `json:"column"`
}

// Range is a half-open source range.
type Range struct {
	Start Position `json:"start"`
	End   Position `json:"end"`
}

// Diagnostic carries the parse-specific metadata, before model admission.
type Diagnostic struct {
	Code         string
	Pointer      string
	Range        Range
	Related      *Range
	AuthoredKeys []string
	Severity     string
	Source       string
}

// Machine returns the stable parse envelope without free-text wording.
func (d Diagnostic) Machine() map[string]any {
	result := map[string]any{"code": d.Code, "path": d.Pointer, "range": d.Range, "stage": "parse", "severity": d.Severity}
	if d.Source != "" {
		result["source"] = d.Source
	}
	if d.AuthoredKeys != nil {
		result["authored_keys"] = slices.Clone(d.AuthoredKeys)
	}
	if d.Related != nil {
		result["related"] = []map[string]any{{"range": *d.Related}}
	}
	return result
}

type parseError struct{ items []Diagnostic }

func (e *parseError) Error() string { return "sdl source rejected" }
func (e *parseError) Code() string {
	if len(e.items) > 0 {
		return e.items[0].Code
	}
	return "sdl.parse"
}
func (e *parseError) Category() fault.Category { return fault.InvalidInput }
func (e *parseError) Unwrap() error            { return nil }

// Diagnostics returns copied source diagnostics from an error chain.
func Diagnostics(err error) []Diagnostic {
	if e, ok := errors.AsType[*parseError](err); ok {
		return copyDiagnostics(e.items)
	}
	return nil
}
func copyDiagnostics(items []Diagnostic) []Diagnostic {
	result := slices.Clone(items)
	for i := range result {
		result[i].AuthoredKeys = slices.Clone(result[i].AuthoredKeys)
		if result[i].Related != nil {
			r := *result[i].Related
			result[i].Related = &r
		}
	}
	return result
}
func failure(code string, r Range, options Options) error {
	return &parseError{[]Diagnostic{{Code: code, Range: r, Source: options.Name, Severity: "error"}}}
}
func startRange() Range { return Range{Position{1, 1}, Position{1, 1}} }

type member struct {
	key, value *node
	canonical  string
}
type node struct {
	kind     byte
	spelling string
	value    any
	entries  []member
	children []*node
	span     Range
	merge    bool
}

// Document holds checked source data. It does not assert SDL model validity.
// Accessors return copies, so caller changes cannot alter checked source state.
type Document struct {
	root              *node
	warnings          []Diagnostic
	ranges, keyRanges map[string]Range
	keyScope          string
}

// Value copies the decoded value, retaining authored field spellings.
func (d *Document) Value() any { return copyValue(d.root, d.keyScope, false) }

// NormalizedValue copies the value with structural field migrations applied.
func (d *Document) NormalizedValue() any { return copyValue(d.root, d.keyScope, true) }

// Diagnostics returns source migration advisories.
func (d *Document) Diagnostics() []Diagnostic { return copyDiagnostics(d.warnings) }

// Ranges returns source ranges indexed by RFC 6901 pointer.
func (d *Document) Ranges() map[string]Range { return maps.Clone(d.ranges) }

// KeyRanges returns declaration-key ranges indexed by RFC 6901 pointer.
func (d *Document) KeyRanges() map[string]Range { return maps.Clone(d.keyRanges) }

func copyValue(n *node, scope string, normalize bool) any {
	switch n.kind {
	case 'm':
		value := make(map[string]any, len(n.entries))
		for _, entry := range n.entries {
			key, _ := entry.key.value.(string)
			if normalize {
				key = canonical(key, scope)
			}
			value[key] = copyValue(entry.value, childScope(scope, canonical(key, scope), entry.value), normalize)
		}
		return value
	case 's':
		value := make([]any, len(n.children))
		for i, c := range n.children {
			value[i] = copyValue(c, scope, normalize)
		}
		return value
	default:
		return n.value
	}
}

// Read bounds a filesystem read before decoding. The caller owns filesystem containment.
// Use a contained fs.FS such as os.Root.FS; os.DirFS alone does not contain symlinks.
func Read(fsys fs.FS, name string, options Options) (*Document, error) {
	if err := options.Limits.Validate(); err != nil {
		return nil, err
	}
	if !fs.ValidPath(name) {
		return nil, fault.New(fault.InvalidInput, "sdl-source-path", nil)
	}
	f, err := fsys.Open(name)
	if err != nil {
		return nil, readFailure(err)
	}
	defer func() { _ = f.Close() }()
	// LimitReader uses int64. Avoid MaxInt64+1 overflow for a trusted custom ceiling.
	bound := options.Limits.MaxInputBytes
	data, err := io.ReadAll(io.LimitReader(f, bound))
	if err != nil {
		return nil, readFailure(err)
	}
	var extra [1]byte
	count, err := io.ReadFull(f, extra[:])
	if err != nil && !errors.Is(err, io.EOF) && !errors.Is(err, io.ErrUnexpectedEOF) {
		return nil, readFailure(err)
	}
	options.Name = name
	if count != 0 {
		return nil, failure("sdl.source_limit", startRange(), options)
	}
	return Decode(data, options)
}

// Decode checks a source graph before constructing or copying its values.
func Decode(data []byte, options Options) (*Document, error) {
	if err := prepare(data, options); err != nil {
		return nil, err
	}
	tokens, err := scan(data, options)
	if err != nil {
		return nil, err
	}
	root, err := compose(tokens, data, options)
	if err != nil {
		return nil, err
	}
	if root == nil {
		return nil, &parseError{}
	}
	err = measure(root, options)
	if err != nil {
		return nil, err
	}
	document := &Document{root: root, keyScope: options.KeyScope, ranges: map[string]Range{}, keyRanges: map[string]Range{}}
	if err := analyze(document, options); err != nil {
		return nil, err
	}
	if err := construct(root, options); err != nil {
		return nil, err
	}
	if options.RequiredRevision != "" && !revisionMatches(root, options.RequiredRevision) {
		return nil, failure("sdl.import.revision-mismatch", startRange(), options)
	}
	if options.RequireMapping && root.kind != 'm' {
		return nil, &parseError{}
	}

	return document, nil
}
func revisionMatches(root *node, revision string) bool {
	if root.kind != 'm' {
		return false
	}
	for _, e := range root.entries {
		if e.key.value == "semantic_revision" {
			return e.value.value == revision
		}
	}
	return false
}

// Keep JSON numbers exact, including arbitrary-precision integers.
func number(text string) json.Number { return json.Number(text) }

func prepare(data []byte, options Options) error {
	if err := options.Limits.Validate(); err != nil {
		return err
	}
	if int64(len(data)) > options.Limits.MaxInputBytes {
		return failure("sdl.source_limit", startRange(), options)
	}
	if !utf8.Valid(data) {
		return failure("sdl.utf8", startRange(), options)
	}
	if strings.TrimSpace(string(data)) == "" {
		return &parseError{}
	}
	if options.MigrationPolicy != "reject" && options.MigrationPolicy != "accept" {
		return failure("sdl.migration_policy", startRange(), options)
	}
	if options.SourceFormat != "sdl-yaml/v1" {
		return failure("sdl.source_format", startRange(), options)
	}
	if options.KeyScope != structuralScope && options.KeyScope != literalScope && options.KeyScope != dataScope {
		return fault.New(fault.InvalidInput, "sdl-key-scope", nil)
	}
	return nil
}

func readFailure(err error) error {
	category := fault.Operational
	code := "sdl-source-unreadable"
	if errors.Is(err, fs.ErrNotExist) {
		category = fault.NotFound
		code = "sdl-source-missing"
	}
	return fault.New(category, code, err)
}

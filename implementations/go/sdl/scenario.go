// Package sdl exposes admitted scenario handles through the native SDL owner.
package sdl

import (
	"bytes"
	"context"
	"encoding/json"
	"io/fs"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// Scenario retains native admission state. Document returns an independent projection.
type Scenario interface {
	Document() map[string]any
	SemanticallyValidated() bool
	admittedScenario()
}

// InstantiatedScenario is a concrete admitted phase with binding provenance.
type InstantiatedScenario interface {
	Scenario
	instantiatedScenario()
}

type scenario struct {
	document        *authoring.Document
	parser          *authoring.Parser
	designationOnce sync.Once
	designations    []designationRecord
	designationErr  error
}
type instantiated struct{ *scenario }

// The native parser owns immutable schemas and request-local composition.
// Retain one default owner; custom limits do not enter an unbounded cache.
var defaultParser = sync.OnceValues(func() (*authoring.Parser, error) { //nolint:gochecknoglobals // The native default owner is immutable; each request owns its source and composition state.
	return authoring.New(nativeLimits(DefaultLimits()))
})

func scenarioParser(limits Limits) (*authoring.Parser, error) {
	if limits == DefaultLimits() {
		return defaultParser()
	}
	return authoring.New(nativeLimits(limits))
}

func newScenario(document *authoring.Document, parser *authoring.Parser) *scenario {
	return &scenario{document: document, parser: parser}
}

func (*scenario) admittedScenario() {
	// This unexported marker seals the handle to its native owner.
}
func (*instantiated) instantiatedScenario() {
	// This unexported marker seals the handle to its native owner.
}

func (s *scenario) SemanticallyValidated() bool {
	return s != nil && s.document != nil && s.document.Validated()
}
func (s *scenario) Document() map[string]any {
	if s == nil || s.document == nil {
		return nil
	}
	decoder := json.NewDecoder(bytes.NewReader(s.document.JSON()))
	decoder.UseNumber()
	var result map[string]any
	if decoder.Decode(&result) != nil {
		panic("sdl: admitted native document is invalid")
	}
	return result
}

// Limits bound source input and the complete composition request.
type Limits struct {
	MaxInputBytes, MaxScalarBytes, MaxComposedBytes              int64
	MaxDepth, MaxNodes, MaxAliases, MaxExpandedNodes, MaxImports int
	MaxComposedNodes, MaxCompositionDepth, MaxNamespaceDepth     int
}

func nativeLimits(limits Limits) source.Limits {
	return source.Limits{
		MaxInputBytes: limits.MaxInputBytes, MaxScalarBytes: limits.MaxScalarBytes, MaxComposedBytes: limits.MaxComposedBytes,
		MaxDepth: limits.MaxDepth, MaxNodes: limits.MaxNodes, MaxAliases: limits.MaxAliases,
		MaxExpandedNodes: limits.MaxExpandedNodes, MaxImports: limits.MaxImports, MaxComposedNodes: limits.MaxComposedNodes,
		MaxCompositionDepth: limits.MaxCompositionDepth, MaxNamespaceDepth: limits.MaxNamespaceDepth,
	}
}

// DefaultLimits returns the source owner's bounded parser and composition limits.
func DefaultLimits() Limits {
	l := source.DefaultLimits()
	return Limits{l.MaxInputBytes, l.MaxScalarBytes, l.MaxComposedBytes, l.MaxDepth, l.MaxNodes, l.MaxAliases,
		l.MaxExpandedNodes, l.MaxImports, l.MaxComposedNodes, l.MaxCompositionDepth, l.MaxNamespaceDepth}
}

// Validate refuses invalid source and composition limits.
func (limits Limits) Validate() error { return nativeLimits(limits).Validate() }

// MigrationPolicy selects whether the native owner may apply supported migrations.
type MigrationPolicy string

// RejectMigration and AcceptMigration select the supported source migration policies.
const (
	RejectMigration MigrationPolicy = "reject"
	AcceptMigration MigrationPolicy = "accept"
	SourceFormat                    = "sdl-yaml/v1"
)

// ParseOptions supplies explicit format, migration, revision, and work limits.
type ParseOptions struct {
	Limits                   Limits
	SourceFormat             string
	MigrationPolicy          MigrationPolicy
	RequiredSemanticRevision string
}

// DefaultParseOptions selects the current SDL format with bounded parsing and no migration.
func DefaultParseOptions() ParseOptions {
	return ParseOptions{Limits: DefaultLimits(), SourceFormat: SourceFormat, MigrationPolicy: RejectMigration}
}

// Validate checks the format, migration policy, and source limits.
func (options ParseOptions) Validate() error {
	if options.SourceFormat != SourceFormat || options.MigrationPolicy != RejectMigration && options.MigrationPolicy != AcceptMigration {
		return invalidScenario()
	}
	return options.Limits.Validate()
}
func invalidScenario() error { return fault.New(fault.InvalidInput, "sdl-scenario-invalid", nil) }

// Parse admits and validates SDL through the native source and semantic owners.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func Parse(source []byte, options ParseOptions) (Scenario, error) {
	return parseRequest(context.Background(), authoring.Request{Source: source}, options, true)
}

// AuthoredScenario parses source without asserting semantic validation.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func AuthoredScenario(source []byte, options ParseOptions) (Scenario, error) {
	return parseRequest(context.Background(), authoring.Request{Source: source}, options, false)
}

// ParseSources composes a bounded, caller-supplied source map and validates its root.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ParseSources(sources map[string][]byte, root string, options ParseOptions) (Scenario, error) {
	if err := options.Validate(); err != nil {
		return nil, err
	}
	var size int64
	for _, raw := range sources {
		if int64(len(raw)) > options.Limits.MaxInputBytes || int64(len(raw)) > options.Limits.MaxComposedBytes-size {
			return nil, invalidScenario()
		}
		size += int64(len(raw))
	}
	return parseRequest(context.Background(), authoring.Request{Source: sources[root], Name: root, Sources: sources}, options, true)
}

// ParseFile composes and validates source within the supplied filesystem.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ParseFile(source fs.FS, root string, options ParseOptions) (Scenario, error) {
	return ParseFileWithContext(context.Background(), source, root, options)
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func parseRequest(ctx context.Context, request authoring.Request, options ParseOptions, validate bool) (Scenario, error) {
	if err := checkParsingContext(ctx); err != nil {
		return nil, err
	}
	if err := options.Validate(); err != nil {
		return nil, err
	}
	decoderOptions := source.DefaultOptions()
	decoderOptions.Limits = nativeLimits(options.Limits)
	decoderOptions.MigrationPolicy = string(options.MigrationPolicy)
	decoderOptions.RequiredRevision = options.RequiredSemanticRevision
	decoderOptions.Name = request.Name
	decoded, err := source.Decode(request.Source, decoderOptions)
	if err != nil {
		return nil, err
	}
	parser, err := scenarioParser(options.Limits)
	if err != nil {
		return nil, err
	}
	if decoded.View().Child("instantiation_provenance").Kind() != "" {
		document, checkErr := parser.AdmitInstantiatedSource(request.Source, string(options.MigrationPolicy))
		if checkErr != nil {
			return nil, checkErr
		}
		if cancelErr := checkParsingContext(ctx); cancelErr != nil {
			return nil, cancelErr
		}
		return &instantiated{&scenario{document: document, parser: parser}}, nil
	}
	document, err := parser.DecodeWithPolicyContext(ctx, request, string(options.MigrationPolicy))
	if err != nil {
		return nil, err
	}
	if validate {
		document, _, err = parser.Validate(document)
		if err != nil {
			return nil, err
		}
	}
	if cancelErr := checkParsingContext(ctx); cancelErr != nil {
		return nil, cancelErr
	}
	return &scenario{document: document, parser: parser}, nil
}

func nativeScenario(input Scenario) (*scenario, error) {
	var result *scenario
	switch s := input.(type) {
	case *scenario:
		result = s
	case *instantiated:
		if s != nil {
			result = s.scenario
		}
	}
	if result == nil || result.document == nil || result.parser == nil {
		return nil, invalidScenario()
	}
	return result, nil
}

// Validate checks an exact native scenario without invoking methods on foreign handles.
func Validate(scenario Scenario) ([]diagnostic.Diagnostic, error) {
	s, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	_, findings, err := s.parser.Validate(s.document)
	return findings, err
}

// Instantiate binds explicit parameters through the native owner and returns a concrete handle.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func Instantiate(scenario Scenario, parameters map[string]any) (InstantiatedScenario, error) {
	s, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	document, err := s.parser.Instantiate(s.document, parameters, "")
	if err != nil {
		return nil, err
	}
	return &instantiated{newScenario(document, s.parser)}, nil
}

// AdmitInstantiated checks the native instantiation envelope and its provenance.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func AdmitInstantiated(scenario Scenario) (InstantiatedScenario, error) {
	s, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	document, err := s.parser.AdmitInstantiated(s.document.JSON())
	if err != nil {
		return nil, err
	}
	return &instantiated{newScenario(document, s.parser)}, nil
}

// AdmitFamily checks a scenario as a family with unresolved parameter authority.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func AdmitFamily(scenario Scenario) (Scenario, error) {
	s, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	document, err := s.parser.AdmitFamily(s.document)
	if err != nil {
		return nil, err
	}
	return newScenario(document, s.parser), nil
}

// CanonicalDigest commits to the native owner's canonical bytes for this phase.
func CanonicalDigest(scenario Scenario) (string, error) {
	s, err := nativeScenario(scenario)
	if err != nil {
		return "", err
	}
	return s.document.CanonicalDigest()
}

// CanonicalBytes returns the native owner's canonical bytes for this phase.
func CanonicalBytes(scenario Scenario) ([]byte, error) {
	input, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	return input.document.CanonicalBytes()
}

// DocumentBytes returns a copy of the validated native document envelope.
func DocumentBytes(scenario Scenario) ([]byte, error) {
	s, err := nativeScenario(scenario)
	if err != nil || !s.document.Validated() {
		return nil, invalidScenario()
	}
	return s.document.JSON(), nil
}

// ModelBytes returns a copy of the validated native scenario model.
func ModelBytes(scenario Scenario) ([]byte, error) {
	s, err := nativeScenario(scenario)
	if err != nil || !s.document.Validated() {
		return nil, invalidScenario()
	}
	return s.document.ModelJSON(), nil
}

// ReferenceBindings returns canonical declarations from the native SDL owner.
func ReferenceBindings(input Scenario) (map[string][]string, error) {
	owned, err := nativeScenario(input)
	if err != nil {
		return nil, err
	}
	return owned.document.ReferenceBindings()
}

// ReferenceBindingsFor keeps purpose-specific resolution with the SDL owner.
func ReferenceBindingsFor(input Scenario, purpose string) (map[string][]string, error) {
	owned, err := nativeScenario(input)
	if err != nil {
		return nil, err
	}
	return owned.document.ReferenceBindingsFor(purpose)
}

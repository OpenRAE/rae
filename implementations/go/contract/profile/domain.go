package profile

import (
	"encoding/json"
	"errors"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/domainprofile"
)

// DomainOperation is one operation that a domain-profile support declaration
// can admit.
type DomainOperation string

// The closed domain-profile operations.
const (
	StructuralValidation DomainOperation = "structural-validation"
	SemanticValidation   DomainOperation = "semantic-validation"
	Refinement           DomainOperation = "refinement"
	Comparison           DomainOperation = "comparison"
	Interpretation       DomainOperation = "interpretation"
	Execution            DomainOperation = "execution"
	TypedReport          DomainOperation = "typed-report"
)

// DomainResolutionOutcome is the result of an exact definition lookup.
type DomainResolutionOutcome string

// The closed resolution outcomes.
const (
	Resolved              DomainResolutionOutcome = "resolved"
	NamespaceUnadmitted   DomainResolutionOutcome = "namespace-unadmitted"
	NamespaceCollision    DomainResolutionOutcome = "namespace-collision"
	DefinitionUnavailable DomainResolutionOutcome = "definition-unavailable"
	IncompatibleRevision  DomainResolutionOutcome = "incompatible-revision"
	DigestMismatch        DomainResolutionOutcome = "digest-mismatch"
	CoordinateCollision   DomainResolutionOutcome = "coordinate-collision"
)

// DomainAdmissionOutcome is the result of one binding admission. Validated
// and OpaquePreserved admit the binding.
type DomainAdmissionOutcome string

// The closed admission outcomes.
const (
	Validated             DomainAdmissionOutcome = "validated"
	OpaquePreserved       DomainAdmissionOutcome = "opaque-preserved"
	ResolutionRefused     DomainAdmissionOutcome = "resolution-refused"
	ContextRefused        DomainAdmissionOutcome = "context-refused"
	UnsupportedOperation  DomainAdmissionOutcome = "unsupported-operation"
	UnsupportedVocabulary DomainAdmissionOutcome = "unsupported-vocabulary"
	UnsupportedKeyword    DomainAdmissionOutcome = "unsupported-keyword"
	SchemaInvalid         DomainAdmissionOutcome = "schema-invalid"
	ValueInvalid          DomainAdmissionOutcome = "value-invalid"
	LimitExceeded         DomainAdmissionOutcome = "limit-exceeded"
)

// DomainLimits bound one resolution context and its admission work.
type DomainLimits struct {
	MaxDefinitions, MaxBindings, MaxDepth, MaxNodes               int
	MaxScalarBytes, MaxReferences, MaxEvaluations, MaxDiagnostics int
}

// DefaultDomainLimits returns the published default limits.
func DefaultDomainLimits() DomainLimits {
	return DomainLimits{MaxDefinitions: 256, MaxBindings: 256, MaxDepth: 16, MaxNodes: 4096, MaxScalarBytes: 1048576, MaxReferences: 128, MaxEvaluations: 65536, MaxDiagnostics: 64}
}

// Validate checks each limit against its published bounds. A limit outside
// its bounds is an InvalidInput fault.
func (limits DomainLimits) Validate() error {
	bounds := []struct{ value, low, high int }{
		{limits.MaxDefinitions, 1, 4096}, {limits.MaxBindings, 1, 4096}, {limits.MaxDepth, 1, 64}, {limits.MaxNodes, 1, 65536},
		{limits.MaxScalarBytes, 1, 16777216}, {limits.MaxReferences, 0, 4096}, {limits.MaxEvaluations, 1, 1048576}, {limits.MaxDiagnostics, 1, 256},
	}
	for _, bound := range bounds {
		if bound.value < bound.low || bound.value > bound.high {
			return invalid("domain-profile-limits-invalid")
		}
	}
	return nil
}

func (limits DomainLimits) inert() validation.InertLimits {
	return validation.InertLimits{MaxBytes: 16777216, MaxDepth: limits.MaxDepth, MaxNodes: limits.MaxNodes, MaxScalarBytes: limits.MaxScalarBytes, MaxReferences: limits.MaxReferences, MaxEvaluations: limits.MaxEvaluations}
}

// DomainCoordinate is the exact immutable coordinate of one definition.
type DomainCoordinate struct{ Namespace, Authority, ProfileID, Revision, DefinitionDigest string }

// DomainProvenance is the source and trust decision of an admitted
// definition.
type DomainProvenance struct{ SourceLocator, SourceDigest, TrustDecisionID string }

// DomainResolution is the result of one exact lookup. Definition and
// Provenance are set only when the outcome is Resolved.
type DomainResolution struct {
	Outcome     DomainResolutionOutcome
	Definition  *binding.DomainProfileDefinitionV1
	Provenance  *DomainProvenance
	Diagnostics []diagnostic.Diagnostic
}

// DomainBindingAdmission is the result of one binding. ResolutionOutcome is
// empty when the admission stopped before resolution.
type DomainBindingAdmission struct {
	BindingID                             string
	Outcome                               DomainAdmissionOutcome
	ResolutionOutcome                     DomainResolutionOutcome
	StructurallyValid, SemanticsSupported bool
	Opaque                                bool
	Provenance                            *DomainProvenance
	Basis                                 string
	Diagnostics                           []diagnostic.Diagnostic
}

// DomainAdmissionReport reports the bindings of one admission request in
// tree order.
type DomainAdmissionReport struct {
	Results              []DomainBindingAdmission
	BindingsTotal        int
	DiagnosticsTruncated bool
}

// Admitted reports whether every binding was reported and admitted.
func (r DomainAdmissionReport) Admitted() bool {
	if r.DiagnosticsTruncated || len(r.Results) != r.BindingsTotal {
		return false
	}
	return !slices.ContainsFunc(r.Results, func(result DomainBindingAdmission) bool {
		return result.Outcome != Validated && result.Outcome != OpaquePreserved
	})
}

const (
	contractBinding  = "domain-profile-binding-v1"
	contractContext  = "domain-profile-resolution-context-v1"
	contractPolicy   = "domain-profile-admission-policy-v1"
	domainDomain     = "domain-profile"
	inputMaxBytes    = 16 << 20
	inputMaxDepth    = 64
	opaqueExchange   = "opaque-exchange"
	defsPrefix       = "#/$defs/"
	severityError    = "error"
	severityWarning  = "warning"
	diagnosticPrefix = "domain-profile."
)

type coordinateWire struct {
	Namespace        string `json:"namespace"`
	Authority        string `json:"authority"`
	ProfileID        string `json:"profile_id"`
	Revision         string `json:"revision"`
	DefinitionDigest string `json:"definition_digest"`
}

type semanticWire struct {
	Authority  string `json:"authority"`
	ContractID string `json:"contract_id"`
	Revision   string `json:"revision"`
	Digest     string `json:"digest"`
}

type definitionWire struct {
	Coordinate    coordinateWire `json:"coordinate"`
	ProfileSchema struct {
		Dialect              *string         `json:"dialect"`
		RequiredVocabularies []string        `json:"required_vocabularies"`
		SchemaDocument       json.RawMessage `json:"schema_document"`
	} `json:"profile_schema"`
	SemanticContract semanticWire `json:"semantic_contract"`
	AllowedContexts  []string     `json:"allowed_contexts"`
}

type admittedWire struct {
	Definition json.RawMessage `json:"definition"`
	Provenance struct {
		SourceLocator   string `json:"source_locator"`
		SourceDigest    string `json:"source_digest"`
		TrustDecisionID string `json:"trust_decision_id"`
	} `json:"provenance"`
	parsed definitionWire
}

type supportWire struct {
	Coordinate       coordinateWire `json:"coordinate"`
	SemanticContract semanticWire   `json:"semantic_contract"`
	Operations       []string       `json:"operations"`
	Dialects         []string       `json:"supported_schema_dialects"`
	Vocabularies     []string       `json:"supported_vocabularies"`
	Keywords         []string       `json:"supported_schema_keywords"`
}

type contextWire struct {
	NamespaceAdmissions []struct {
		Namespace string `json:"namespace"`
		Authority string `json:"authority"`
	} `json:"namespace_admissions"`
	Definitions []admittedWire         `json:"definitions"`
	Supports    []supportWire          `json:"support_declarations"`
	Limits      map[string]json.Number `json:"limits"`
	limits      DomainLimits
}

type bindingWire struct {
	BindingID  string         `json:"binding_id"`
	Coordinate coordinateWire `json:"coordinate"`
	Owner      struct {
		Context string `json:"context"`
		Use     string `json:"use"`
	} `json:"owner"`
	Value      json.RawMessage `json:"value"`
	Provenance struct {
		Basis string `json:"basis"`
	} `json:"provenance"`
	Children []bindingWire `json:"children"`
}

type policyWire struct {
	RequiredOperations  []string `json:"required_operations"`
	AllowOpaqueExchange bool     `json:"allow_opaque_exchange"`
}

func inputInvalid() error { return invalid("domain-profile-input-invalid") }

// checkInput applies the published schema and the shared model rules to one
// transport value and decodes it into its wire form.
func (p *Profiles) checkInput(contract string, value, target any) error {
	data, err := json.Marshal(value)
	if err != nil {
		return inputInvalid()
	}
	if err := p.checkDocument(contract, data); err != nil {
		return err
	}
	if json.Unmarshal(data, target) != nil {
		return inputInvalid()
	}
	return nil
}

func (p *Profiles) checkDocument(contract string, data []byte) error {
	checkedRoot := false
	err := p.schemas.CheckInstances(contract, data, ingress.Limits{MaxBytes: inputMaxBytes, MaxDepth: inputMaxDepth}, func(instance validation.SchemaInstance) error {
		if !checkedRoot {
			checkedRoot = true
			if _, rootErr := domainprofile.CheckModel(contract, instance.Root); rootErr != nil {
				return rootErr
			}
		}
		_, modelErr := domainprofile.CheckModel(strings.TrimPrefix(instance.SchemaPointer, defsPrefix), instance.Value)
		return modelErr
	})
	if err != nil {
		return inputInvalid()
	}
	return nil
}

// decodeContext checks one context document. The document bytes keep the
// member order of each profile schema, which fixes the order in which the
// bounded evaluator visits its keywords.
func (p *Profiles) decodeContext(context []byte) (contextWire, error) {
	if err := p.checkDocument(contractContext, context); err != nil {
		return contextWire{}, err
	}
	var wire contextWire
	if json.Unmarshal(context, &wire) != nil {
		return contextWire{}, inputInvalid()
	}
	for i := range wire.Definitions {
		if json.Unmarshal(wire.Definitions[i].Definition, &wire.Definitions[i].parsed) != nil {
			return contextWire{}, inputInvalid()
		}
	}
	wire.limits = contextLimits(wire.Limits)
	return wire, nil
}

// contextLimits applies the published defaults to the schema-checked limits.
func contextLimits(values map[string]json.Number) DomainLimits {
	defaults := DefaultDomainLimits()
	members := map[string]any{}
	for name, value := range values {
		members[name] = value
	}
	pick := func(name string, fallback int) int { return domainprofile.Limit(members, name, fallback) }
	return DomainLimits{
		MaxDefinitions: pick("max_definitions", defaults.MaxDefinitions), MaxBindings: pick("max_bindings", defaults.MaxBindings),
		MaxDepth: pick("max_depth", defaults.MaxDepth), MaxNodes: pick("max_nodes", defaults.MaxNodes),
		MaxScalarBytes: pick("max_scalar_bytes", defaults.MaxScalarBytes), MaxReferences: pick("max_references", defaults.MaxReferences),
		MaxEvaluations: pick("max_evaluations", defaults.MaxEvaluations), MaxDiagnostics: pick("max_diagnostics", defaults.MaxDiagnostics),
	}
}

// ResolveDomainProfile selects one exact definition from the supplied local
// context document, without discovery. It refuses a context that is not a
// valid domain-profile-resolution-context-v1 document with an InvalidInput
// fault.
func (p *Profiles) ResolveDomainProfile(coordinate DomainCoordinate, context []byte) (DomainResolution, error) {
	wire, err := p.decodeContext(context)
	if err != nil {
		return DomainResolution{}, err
	}
	resolution, _, err := resolve(coordinateWire(coordinate), wire)
	return resolution, err
}

// resolutionMessages returns the fixed message of each refusal.
func resolutionMessages() map[DomainResolutionOutcome]string {
	return map[DomainResolutionOutcome]string{
		NamespaceCollision:    "the profile namespace resolves to conflicting admitted authorities",
		NamespaceUnadmitted:   "the profile namespace is not admitted for the requested authority",
		DefinitionUnavailable: "the requested profile definition is absent from the supplied local context",
		IncompatibleRevision:  "the supplied profile definitions do not contain the exact requested revision",
		CoordinateCollision:   "the same logical profile coordinate resolves to conflicting definition digests",
		DigestMismatch:        "the supplied profile definition digest does not match the exact request",
	}
}

func refusedResolution(outcome DomainResolutionOutcome) DomainResolution {
	return refused(outcome, resolutionMessages()[outcome])
}

func refused(outcome DomainResolutionOutcome, message string) DomainResolution {
	return DomainResolution{Outcome: outcome, Diagnostics: []diagnostic.Diagnostic{{Code: diagnosticPrefix + string(outcome), Severity: severityError, Domain: domainDomain, Address: "#", Message: message}}}
}

func resolve(coordinate coordinateWire, context contextWire) (DomainResolution, definitionWire, error) {
	if outcome := namespaceOutcome(coordinate, context); outcome != "" {
		return refusedResolution(outcome), definitionWire{}, nil
	}
	selected, outcome := selectDefinition(coordinate, context)
	if outcome == CoordinateCollision && selected != nil {
		return refused(CoordinateCollision, "the exact profile coordinate resolves to multiple supplied definitions"), definitionWire{}, nil
	}
	if outcome != "" {
		return refusedResolution(outcome), definitionWire{}, nil
	}
	var definition binding.DomainProfileDefinitionV1
	if json.Unmarshal(selected.Definition, &definition) != nil {
		return DomainResolution{}, definitionWire{}, inputInvalid()
	}
	provenance := DomainProvenance(selected.Provenance)
	return DomainResolution{Outcome: Resolved, Definition: &definition, Provenance: &provenance}, selected.parsed, nil
}

// namespaceOutcome requires exactly the requested authority for the
// namespace.
func namespaceOutcome(coordinate coordinateWire, context contextWire) DomainResolutionOutcome {
	authorities := map[string]bool{}
	for _, admission := range context.NamespaceAdmissions {
		if admission.Namespace == coordinate.Namespace {
			authorities[admission.Authority] = true
		}
	}
	if len(authorities) > 1 {
		return NamespaceCollision
	}
	if !authorities[coordinate.Authority] {
		return NamespaceUnadmitted
	}
	return ""
}

// selectDefinition narrows the definitions by identity, revision and digest.
// It returns the duplicate with CoordinateCollision when the exact
// coordinate matches more than one definition.
func selectDefinition(coordinate coordinateWire, context contextWire) (*admittedWire, DomainResolutionOutcome) {
	identity, revision := 0, 0
	digests := map[string]bool{}
	var exact []admittedWire
	for _, item := range context.Definitions {
		candidate := item.parsed.Coordinate
		if candidate.Namespace != coordinate.Namespace || candidate.Authority != coordinate.Authority || candidate.ProfileID != coordinate.ProfileID {
			continue
		}
		identity++
		if candidate.Revision != coordinate.Revision {
			continue
		}
		revision++
		digests[candidate.DefinitionDigest] = true
		if candidate.DefinitionDigest == coordinate.DefinitionDigest {
			exact = append(exact, item)
		}
	}
	return narrowed(identity, revision, len(digests), exact)
}

func narrowed(identity, revision, digests int, exact []admittedWire) (*admittedWire, DomainResolutionOutcome) {
	if identity == 0 {
		return nil, DefinitionUnavailable
	}
	if revision == 0 {
		return nil, IncompatibleRevision
	}
	if digests > 1 {
		return nil, CoordinateCollision
	}
	if len(exact) == 0 {
		return nil, DigestMismatch
	}
	if len(exact) > 1 {
		return &exact[1], CoordinateCollision
	}
	return &exact[0], ""
}

// admissionMessages returns the fixed message of each refusal outcome.
func admissionMessages() map[DomainAdmissionOutcome]string {
	return map[DomainAdmissionOutcome]string{
		OpaquePreserved:       "the unresolved profile value is preserved as non-binding opaque data without semantic claims",
		ResolutionRefused:     "the exact required profile definition could not be resolved from the supplied local context",
		ContextRefused:        "the profile definition does not permit the requested host context",
		UnsupportedOperation:  "the exact profile and semantic contract lack support for a required operation",
		UnsupportedVocabulary: "the structural validator does not support every required schema vocabulary",
		UnsupportedKeyword:    "the profile schema uses a keyword outside the admitted safe subset",
		SchemaInvalid:         "the supplied profile schema is not safely admissible",
		ValueInvalid:          "the profile value does not satisfy its exact schema",
		LimitExceeded:         "domain profile admission exhausted a configured limit",
	}
}

// admissionResult builds one result. Without explicit diagnostics, a
// refusal carries the diagnostic of its outcome.
func admissionResult(b bindingWire, outcome DomainAdmissionOutcome, resolution DomainResolutionOutcome, diagnostics []diagnostic.Diagnostic) DomainBindingAdmission {
	if diagnostics == nil && outcome != Validated {
		severity := severityError
		if outcome == OpaquePreserved {
			severity = severityWarning
		}
		diagnostics = []diagnostic.Diagnostic{{Code: diagnosticPrefix + string(outcome), Severity: severity, Domain: domainDomain, Address: "#", Message: admissionMessages()[outcome]}}
	}
	return DomainBindingAdmission{BindingID: b.BindingID, Outcome: outcome, ResolutionOutcome: resolution, StructurallyValid: outcome == Validated, Opaque: outcome == OpaquePreserved, Basis: b.Provenance.Basis, Diagnostics: diagnostics}
}

// AdmitDomainBindings resolves and admits every binding against the context
// document before a caller changes state. The context is a
// domain-profile-resolution-context-v1 document; its bytes keep the member
// order of each profile schema. It refuses inputs that are not valid
// published documents with an InvalidInput fault.
func (p *Profiles) AdmitDomainBindings(bindings []binding.DomainProfileBindingV1, context []byte, policy binding.DomainProfileAdmissionPolicyV1) (DomainAdmissionReport, error) {
	ctx, err := p.decodeContext(context)
	if err != nil {
		return DomainAdmissionReport{}, err
	}
	var rules policyWire
	if err := p.checkInput(contractPolicy, policy, &rules); err != nil {
		return DomainAdmissionReport{}, err
	}
	roots := make([]bindingWire, len(bindings))
	for i, b := range bindings {
		if err := p.checkInput(contractBinding, b, &roots[i]); err != nil {
			return DomainAdmissionReport{}, err
		}
	}
	return admitBindings(roots, ctx, rules), nil
}

func admitBindings(roots []bindingWire, ctx contextWire, policy policyWire) DomainAdmissionReport {
	if len(roots) == 0 {
		return DomainAdmissionReport{}
	}
	flattened, outcome := flatten(roots, ctx.limits)
	if outcome != "" {
		return DomainAdmissionReport{Results: []DomainBindingAdmission{admissionResult(roots[0], outcome, "", nil)}, BindingsTotal: len(roots)}
	}
	report := DomainAdmissionReport{BindingsTotal: len(flattened)}
	count := 0
	for _, b := range flattened {
		result := admitOne(b, ctx, policy)
		if count+len(result.Diagnostics) > ctx.limits.MaxDiagnostics {
			report.DiagnosticsTruncated = true
			break
		}
		report.Results = append(report.Results, result)
		count += len(result.Diagnostics)
	}
	return report
}

// flatten visits the binding tree in order within the depth and count
// limits. Binding IDs must be unique in one request.
func flatten(roots []bindingWire, limits DomainLimits) ([]bindingWire, DomainAdmissionOutcome) {
	var flattened []bindingWire
	var visit func(bindingWire, int) bool
	visit = func(b bindingWire, depth int) bool {
		if depth > limits.MaxDepth || len(flattened) >= limits.MaxBindings {
			return false
		}
		flattened = append(flattened, b)
		for _, child := range b.Children {
			if !visit(child, depth+1) {
				return false
			}
		}
		return true
	}
	for _, root := range roots {
		if !visit(root, 0) {
			return nil, LimitExceeded
		}
	}
	ids := map[string]bool{}
	for _, b := range flattened {
		ids[b.BindingID] = true
	}
	if len(ids) != len(flattened) {
		return nil, ResolutionRefused
	}
	return flattened, ""
}

// operationsByUse returns the operations that each binding use requires.
func operationsByUse() map[string][]string {
	return map[string][]string{
		"constraint":   {string(SemanticValidation), string(StructuralValidation)},
		"typed-report": {string(StructuralValidation), string(TypedReport)},
		"annotation":   {string(StructuralValidation)},
		opaqueExchange: nil,
	}
}

func requiredOperations(b bindingWire, policy policyWire) []string {
	required := slices.Concat(operationsByUse()[b.Owner.Use], policy.RequiredOperations)
	slices.Sort(required)
	return slices.Compact(required)
}

func admitOne(b bindingWire, ctx contextWire, policy policyWire) DomainBindingAdmission {
	required := requiredOperations(b, policy)
	resolution, definition, err := resolve(b.Coordinate, ctx)
	if err != nil {
		return admissionResult(b, ResolutionRefused, "", nil)
	}
	if resolution.Outcome != Resolved {
		return admitUnresolved(b, ctx, policy, required, resolution)
	}
	return admitResolved(b, ctx, definition, required, resolution)
}

func admitUnresolved(b bindingWire, ctx contextWire, policy policyWire, required []string, resolution DomainResolution) DomainBindingAdmission {
	opaque := b.Owner.Use == opaqueExchange && policy.AllowOpaqueExchange && len(required) == 0
	if resolution.Outcome != DefinitionUnavailable || !opaque {
		return admissionResult(b, ResolutionRefused, resolution.Outcome, resolution.Diagnostics)
	}
	if outcome := inertOutcome(validation.InspectInertValue(b.Value, ctx.limits.inert())); outcome != "" {
		return admissionResult(b, outcome, resolution.Outcome, nil)
	}
	return admissionResult(b, OpaquePreserved, resolution.Outcome, nil)
}

func admitResolved(b bindingWire, ctx contextWire, parsed definitionWire, required []string, resolution DomainResolution) DomainBindingAdmission {
	if !slices.Contains(parsed.AllowedContexts, b.Owner.Context) {
		return admissionResult(b, ContextRefused, resolution.Outcome, nil)
	}
	selected := required
	if len(selected) == 0 {
		selected = []string{string(StructuralValidation)}
	}
	support, ok := matchingSupport(parsed, ctx)
	if !ok || !subset(selected, support.Operations) {
		return admissionResult(b, UnsupportedOperation, resolution.Outcome, nil)
	}
	if slices.Contains(selected, string(StructuralValidation)) {
		if outcome := structuralOutcome(b, parsed, support, ctx.limits); outcome != "" {
			return admissionResult(b, outcome, resolution.Outcome, nil)
		}
	}
	result := admissionResult(b, Validated, resolution.Outcome, nil)
	result.SemanticsSupported = slices.ContainsFunc(support.Operations, func(op string) bool { return op != string(StructuralValidation) })
	result.Provenance = resolution.Provenance
	return result
}

// matchingSupport returns the single declaration for the exact coordinate
// and semantic contract.
func matchingSupport(definition definitionWire, ctx contextWire) (supportWire, bool) {
	var matches []supportWire
	for _, declaration := range ctx.Supports {
		if declaration.Coordinate == definition.Coordinate && declaration.SemanticContract == definition.SemanticContract {
			matches = append(matches, declaration)
		}
	}
	if len(matches) != 1 {
		return supportWire{}, false
	}
	return matches[0], true
}

func structuralOutcome(b bindingWire, definition definitionWire, support supportWire, limits DomainLimits) DomainAdmissionOutcome {
	dialect := domainprofile.Dialect
	if definition.ProfileSchema.Dialect != nil {
		dialect = *definition.ProfileSchema.Dialect
	}
	if !slices.Contains(support.Dialects, dialect) || !subset(definition.ProfileSchema.RequiredVocabularies, support.Vocabularies) {
		return UnsupportedVocabulary
	}
	return inertOutcome(validation.CheckInertSchema(definition.ProfileSchema.SchemaDocument, b.Value, support.Keywords, limits.inert()))
}

// inertOutcome maps a result of the inert schema engine to its admission
// outcome.
func inertOutcome(err error) DomainAdmissionOutcome {
	if err == nil {
		return ""
	}
	var refusal *fault.Error
	if !errors.As(err, &refusal) {
		return SchemaInvalid
	}
	switch refusal.Code() {
	case validation.InertLimitExceeded:
		return LimitExceeded
	case validation.InertUnsupportedKeyword:
		return UnsupportedKeyword
	case validation.InertValueInvalid:
		return ValueInvalid
	}
	return SchemaInvalid
}

func subset(values, allowed []string) bool {
	for _, value := range values {
		if !slices.Contains(allowed, value) {
			return false
		}
	}
	return true
}

// ParseDomainBinding parses one bounded binding without duplicate members.
// It checks the limits, the value budget, the published schema and the model
// rules, and returns an InvalidInput fault for any failure.
func (p *Profiles) ParseDomainBinding(data []byte, maxBytes int, limits DomainLimits) (binding.DomainProfileBindingV1, error) {
	if maxBytes < 1 {
		return binding.DomainProfileBindingV1{}, invalid("domain-profile-limits-invalid")
	}
	if err := limits.Validate(); err != nil {
		return binding.DomainProfileBindingV1{}, err
	}
	if _, err := ingress.Parse(data, ingress.Limits{MaxBytes: maxBytes}, ingress.Object); err != nil {
		return binding.DomainProfileBindingV1{}, inputInvalid()
	}
	if err := validation.InspectInertValue(data, limits.inert()); err != nil {
		return binding.DomainProfileBindingV1{}, inputInvalid()
	}
	if err := p.checkDocument(contractBinding, data); err != nil {
		return binding.DomainProfileBindingV1{}, err
	}
	var parsed binding.DomainProfileBindingV1
	if json.Unmarshal(data, &parsed) != nil {
		return binding.DomainProfileBindingV1{}, inputInvalid()
	}
	return parsed, nil
}

// DomainDefinitionDigest returns the RFC 8785 digest of the definition
// projection without its own digest. It does not admit the definition.
func DomainDefinitionDigest(definition binding.DomainProfileDefinitionV1) (string, error) {
	data, err := json.Marshal(definition)
	if err != nil {
		return "", inputInvalid()
	}
	value, err := domainprofile.Decode(data)
	if err != nil {
		return "", inputInvalid()
	}
	digest, err := domainprofile.DefinitionDigest(value)
	if err != nil {
		return "", inputInvalid()
	}
	return digest, nil
}

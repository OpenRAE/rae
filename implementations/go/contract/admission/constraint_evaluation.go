package admission

import (
	"bytes"
	"encoding/json"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// ConstraintLimits bounds semantic traversal separately from JSON admission.
type ConstraintLimits struct {
	MaxDepth, MaxNodes, MaxOperations, MaxMembers, MaxIdentityChecks, MaxReferenceHops int
	MaxScalarBytes, MaxTotalScalarBytes, MaxDiagnostics                                int
	MaxDocumentScalarBytes                                                             *int
}

// DefaultConstraintLimits returns the shared recursive relation work budget.
func DefaultConstraintLimits() ConstraintLimits {
	l := value.Default()
	return ConstraintLimits{l.MaxDepth, l.MaxNodes, l.MaxOperations, l.MaxMembers, l.MaxIdentityChecks,
		l.MaxReferenceHops, l.MaxScalarBytes, l.MaxTotalScalarBytes, l.MaxDiagnostics, nil}
}
func (limits ConstraintLimits) native() value.Limits {
	l := value.Limits{MaxDepth: limits.MaxDepth, MaxNodes: limits.MaxNodes, MaxOperations: limits.MaxOperations,
		MaxMembers: limits.MaxMembers, MaxIdentityChecks: limits.MaxIdentityChecks, MaxReferenceHops: limits.MaxReferenceHops,
		MaxScalarBytes: limits.MaxScalarBytes, MaxTotalScalarBytes: limits.MaxTotalScalarBytes, MaxDiagnostics: limits.MaxDiagnostics}
	if limits.MaxDocumentScalarBytes != nil {
		l.MaxDocumentScalarBytes = *limits.MaxDocumentScalarBytes
	}
	return l
}

// Validate refuses invalid or unbounded work limits.
func (limits ConstraintLimits) Validate() error {
	if limits.MaxDocumentScalarBytes != nil && *limits.MaxDocumentScalarBytes == 0 {
		return fault.New(fault.InvalidInput, "constraint-limit-definition", nil)
	}
	return limits.native().Validate()
}

type constraintClosure struct {
	Posture  string `json:"posture"`
	Universe string `json:"universe"`
	Profile  string `json:"profile"`
}
type constraintField struct {
	name string
	rule *constraintNode
}
type constraintFields []constraintField

func (fields *constraintFields) UnmarshalJSON(raw []byte) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if token, err := decoder.Token(); err != nil || token != json.Delim('{') {
		return invalid()
	}
	for decoder.More() {
		name, err := decoder.Token()
		if err != nil {
			return err
		}
		var node constraintNode
		if err := decoder.Decode(&node); err != nil {
			return err
		}
		fieldName, valid := name.(string)
		if !valid {
			return invalid()
		}
		*fields = append(*fields, constraintField{name: fieldName, rule: &node})
	}
	_, err := decoder.Token()
	return err
}

type constraintNode struct {
	fieldIndex     map[string]*constraintNode
	Kind           string            `json:"kind"`
	Presence       string            `json:"presence"`
	Origin         string            `json:"origin"`
	State          string            `json:"state"`
	Target         string            `json:"target"`
	Value          any               `json:"value"`
	Domain         any               `json:"domain"`
	Fields         constraintFields  `json:"fields"`
	Items          []*constraintNode `json:"items"`
	Constraints    []*constraintNode `json:"constraints"`
	Closure        constraintClosure `json:"closure"`
	MinItems       int               `json:"min_items"`
	MaxItems       *int              `json:"max_items"`
	CollectionKind string            `json:"collection_kind"`
	CyclePolicy    string            `json:"cycle_policy"`
	IdentityFields []string          `json:"identity_fields"`
	Members        []struct {
		Identity   []any           `json:"identity"`
		Constraint *constraintNode `json:"constraint"`
	} `json:"members"`
	Aliases []struct {
		Identity []any `json:"identity"`
		Target   []any `json:"target"`
	} `json:"aliases"`
}
type constraintScope struct {
	Pointer string            `json:"field_pointer"`
	Closure constraintClosure `json:"closure"`
	Origin  string            `json:"origin"`
}
type constraintDocument struct {
	Root           *constraintNode   `json:"root"`
	DefaultClosure constraintClosure `json:"default_closure"`
	Scopes         []constraintScope `json:"scopes"`
	Definitions    constraintFields  `json:"definitions"`
}

type constraintFinding struct {
	Code     string `json:"code"`
	Domain   string `json:"domain"`
	Address  string `json:"address"`
	Message  string `json:"message"`
	Severity string `json:"severity"`
}
type constraintResult struct {
	Status      string              `json:"status"`
	Diagnostics []constraintFinding `json:"diagnostics"`
}

func constraintSuccess() constraintResult {
	return constraintResult{Status: assuranceConformant, Diagnostics: []constraintFinding{}}
}
func constraintFailure(status, address, message string) constraintResult {
	return constraintResult{Status: status, Diagnostics: []constraintFinding{{Code: "realization." + status,
		Domain: "realization", Address: address, Message: message, Severity: termError}}}
}
func constraintCombine(results []constraintResult, maximum int) constraintResult {
	for _, status := range []string{termLimitExceeded, "invalid", statusUnsupported, "nonconformant", "unresolved"} {
		combined := constraintResult{Status: status, Diagnostics: []constraintFinding{}}
		matched := false
		for _, result := range results {
			if result.Status == status {
				matched = true
				remaining := maximum - len(combined.Diagnostics)
				combined.Diagnostics = append(combined.Diagnostics, result.Diagnostics[:min(remaining, len(result.Diagnostics))]...)
			}
		}
		if matched {
			return combined
		}
	}
	return constraintSuccess()
}

type constraintEvaluation struct {
	scopes                        *constraintScopeIndex
	document                      constraintDocument
	limits                        ConstraintLimits
	nodes, operations, identities int
}

func (e *constraintEvaluation) spend(depth int) bool {
	e.nodes++
	e.operations++
	return depth <= e.limits.MaxDepth && e.nodes <= e.limits.MaxNodes && e.operations <= e.limits.MaxOperations
}

// EvaluateRealizationConstraint accepts only the shared owner's sealed fragments.
// A callback that embeds Fragment cannot replace admitted document bytes.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func EvaluateRealizationConstraint(constraint, actual Fragment, limits ConstraintLimits) (Fragment, error) {
	if err := limits.Validate(); err != nil {
		return nil, err
	}
	rule, ruleOK := constraint.(fragment)
	observed, observedOK := actual.(fragment)
	if !ruleOK || !observedOK || rule.profile != RealizationConstraint || observed.profile != RealizationValue {
		return nil, fragmentInvalid()
	}
	var document constraintDocument
	decoder := json.NewDecoder(bytes.NewReader(rule.data))
	decoder.UseNumber()
	if decoder.Decode(&document) != nil || document.Root == nil {
		return nil, fragmentInvalid()
	}
	engine := constraintEvaluation{document: document, limits: limits}
	actualValue := observed.Document()
	var result constraintResult
	observedWork := constraintValueAdmission{engine: &engine}
	// The admission layer already bounds the immutable input carriers. These
	// checks enforce the relation caller's narrower work limits before evaluation.
	failure := constraintWorkFailure(document, object(rule.Document()), limits)
	switch {
	case failure != nil:
		result = *failure
	case !observedWork.walk(actualValue, "", 0):
		result = *observedWork.failure
	case !engine.indexScopes():
		result = constraintFailure(termLimitExceeded, "", "Scope indexing exceeded max_operations.")
	default:
		overlays := engine.scopeOverlays(actualValue)
		root := engine.evaluate(document.Root, actualValue, "", 0, nil)
		result = constraintCombine(append([]constraintResult{root}, overlays...), limits.MaxDiagnostics)
	}
	raw, err := json.Marshal(result)
	if err != nil {
		return nil, err
	}
	return fragment{profile: RealizationConstraintEvaluation, data: raw}, nil
}

func (e *constraintEvaluation) evaluate(rule *constraintNode, actual any, pointer string, depth int, references []string) constraintResult {
	if !e.spend(depth) {
		return constraintFailure(termLimitExceeded, pointer, "Recursive realization evaluation exceeded bounded work limits.")
	}
	switch rule.Kind {
	case kindLiteral:
		if rule.Value == nil && actual == nil || domain.Equal(rule.Value, actual) {
			return constraintSuccess()
		}
		return constraintFailure("nonconformant", pointer, "Observed value does not satisfy the exact typed constraint.")
	case "knowledge":
		return constraintFailure("unresolved", pointer, "The "+rule.State+" knowledge state cannot establish conformance.")
	case termDelegated:
		return constraintSuccess()
	case fieldDomain, termGraphReference:
		return e.domain(rule, actual, pointer)
	case kindRecursiveRecord:
		return e.record(rule, actual, pointer, depth, references)
	case termSequence:
		return e.sequence(rule, actual, pointer, depth, references)
	case termKeyedCollection:
		return e.keyed(rule, actual, pointer, depth, references)
	case "definition-reference":
		return e.reference(rule, actual, pointer, depth, references)
	case termAllOf:
		return e.allOf(rule, actual, pointer, depth, references)
	default:
		return constraintFailure(statusUnsupported, pointer, "Constraint kind has no selected evaluator.")
	}
}

func (e *constraintEvaluation) domain(rule *constraintNode, actual any, pointer string) constraintResult {
	if stringAt(rule.Domain, termKind) == "null" {
		if actual == nil {
			return constraintSuccess()
		}
		return constraintFailure("nonconformant", pointer, "Observed value is outside the declared bounded domain.")
	}
	if stringAt(rule.Domain, termKind) == termVersion {
		descriptor, err := modelVersionDomain(rule.Domain)
		if err != nil {
			return constraintFailure("invalid", pointer, "Version domain is invalid.")
		}
		status := string(descriptor.Membership(actual))
		if status == assuranceConformant {
			return constraintSuccess()
		}
		return constraintFailure(status, pointer, "Version predicate evaluated under its selected relation.")
	}
	descriptor, err := envelopeDomain(rule.Domain)
	if err != nil {
		return constraintFailure("invalid", pointer, "Bounded domain is invalid.")
	}
	matches, err := domain.In(actual, descriptor)
	if err == nil && matches {
		return constraintSuccess()
	}
	return constraintFailure("nonconformant", pointer, "Observed value is outside the declared bounded domain.")
}

func (e *constraintEvaluation) record(rule *constraintNode, actual any, pointer string, depth int, references []string) constraintResult {
	observed, ok := actual.(map[string]any)
	if !ok {
		return constraintFailure("nonconformant", pointer, "Observed value is not a record required by the recursive constraint.")
	}
	results := []constraintResult{}
	declared := make(map[string]bool, len(rule.Fields))
	for _, field := range rule.Fields {
		declared[field.name] = true
		child, present := observed[field.name]
		results = append(results, e.member(field.rule, child, present, pointer+"/"+jsonpointer.EscapeToken(field.name), depth, references, "member"))
	}
	extras := false
	for name := range observed {
		extras = extras || !declared[name]
	}
	results = append(results, e.closure(rule.Closure, pointer, extras, "record"))
	return constraintCombine(results, e.limits.MaxDiagnostics)
}

func (e *constraintEvaluation) sequence(rule *constraintNode, actual any, pointer string, depth int, references []string) constraintResult {
	observed, ok := actual.([]any)
	if !ok {
		return constraintFailure("nonconformant", pointer, "Observed value is not the required ordered sequence.")
	}
	maximum := 4096
	if rule.MaxItems != nil {
		maximum = *rule.MaxItems
	}
	if len(observed) < rule.MinItems || len(observed) > maximum {
		return constraintFailure("nonconformant", pointer, "Observed sequence violates its declared cardinality.")
	}
	results := []constraintResult{}
	for index, child := range rule.Items {
		var item any
		if index < len(observed) {
			item = observed[index]
		}
		results = append(results, e.member(child, item, index < len(observed), pointer+"/"+strconv.Itoa(index), depth, references, "sequence occurrence"))
	}
	results = append(results, e.closure(rule.Closure, pointer, len(observed) > len(rule.Items), "ordered sequence"))
	return constraintCombine(results, e.limits.MaxDiagnostics)
}

func (e *constraintEvaluation) reference(rule *constraintNode, actual any, pointer string, depth int, references []string) constraintResult {
	if len(references) >= e.limits.MaxReferenceHops {
		return constraintFailure(termLimitExceeded, pointer, "Constraint definition resolution exceeded max_reference_hops.")
	}
	if slices.Contains(references, rule.Target) {
		return constraintFailure("invalid", pointer, "Constraint definitions contain a reference cycle.")
	}
	for _, definition := range e.document.Definitions {
		if definition.name == rule.Target {
			return e.evaluate(definition.rule, actual, pointer, depth, append(slices.Clone(references), rule.Target))
		}
	}
	return constraintFailure("invalid", pointer, "Constraint definition reference does not resolve in this document.")
}

func (e *constraintEvaluation) allOf(rule *constraintNode, actual any, pointer string, depth int, references []string) constraintResult {
	results := make([]constraintResult, len(rule.Constraints))
	for index, child := range rule.Constraints {
		results[index] = e.evaluate(child, actual, pointer, depth, references)
	}
	return constraintCombine(results, e.limits.MaxDiagnostics)
}

func (e *constraintEvaluation) member(rule *constraintNode, actual any, present bool, pointer string, depth int, references []string, kind string) constraintResult {
	if rule.Presence == termForbidden && present {
		return constraintFailure("nonconformant", pointer, "A forbidden "+kind+" is present.")
	}
	if rule.Presence != termOptional && rule.Presence != termForbidden && !present {
		return constraintFailure("nonconformant", pointer, "A required "+kind+" is absent.")
	}
	if !present || rule.Presence == termForbidden {
		return constraintSuccess()
	}
	return e.evaluate(rule, actual, pointer, depth+1, references)
}

func (e *constraintEvaluation) closure(local constraintClosure, pointer string, extras bool, kind string) constraintResult {
	closure := local
	if closure.Posture == "" || closure.Posture == termUndefined {
		var valid bool
		closure, valid = e.inheritedClosure(pointer)
		if !valid {
			return constraintFailure(termLimitExceeded, pointer, "Closure resolution exceeded max_operations.")
		}
	}
	if closure.Posture == "" || closure.Posture == termUndefined {
		return constraintFailure(statusUnsupported, pointer, "No effective closure policy is selected for this "+kind+".")
	}
	if closure.Posture == termClosed && extras {
		if kind == "ordered sequence" {
			return constraintFailure("nonconformant", pointer, "A closed ordered sequence contains additional occurrences.")
		}
		if kind == "keyed collection" {
			return constraintFailure("nonconformant", pointer, "A closed keyed collection contains an additional member in its named universe.")
		}
		return constraintFailure("nonconformant", pointer, "A closed "+kind+" contains an undeclared member in its named universe.")
	}
	return constraintSuccess()
}

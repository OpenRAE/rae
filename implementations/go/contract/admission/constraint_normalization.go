package admission

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strconv"
	"strings"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// RealizationClosure names the closure posture and the universe it governs.
type RealizationClosure struct{ Posture, Universe, Profile string }

// RealizationScope applies a closure rule at a canonical field pointer.
type RealizationScope struct {
	FieldPointer string
	Closure      RealizationClosure
	Origin       string
}

// RealizationCollectionProfile declares collection identity independently of item order.
type RealizationCollectionProfile struct {
	FieldPointer, CollectionKind string
	IdentityFields               []string
	Closure                      RealizationClosure
}

// RealizationNormalizationMetadata supplies admitted source authority for literal lowering.
type RealizationNormalizationMetadata struct {
	Scopes             []RealizationScope
	CollectionProfiles []RealizationCollectionProfile
	Origins            map[string]string
	LeafConstraints    map[string]Fragment
	OptionalFields     []string
	MemberPresence     map[string]string
}

// RealizationConstraintBuildResult reports conformance or a bounded, value-free refusal.
type RealizationConstraintBuildResult struct {
	Status      string
	Document    Fragment
	Diagnostics []diagnostic.Diagnostic
}

var normalizationOwner = sync.OnceValues(New) //nolint:gochecknoglobals // The packaged validator has no request state.

func normalizationFailure(status, pointer, message string) RealizationConstraintBuildResult {
	return RealizationConstraintBuildResult{Status: status, Diagnostics: []diagnostic.Diagnostic{{Code: "realization." + status, Domain: "realization", Address: pointer, Message: message, Severity: termError}}}
}

func normalizationClosure(input RealizationClosure) map[string]any {
	return constraintClosureMetadata(constraintClosure(input))
}

type literalNormalizer struct {
	limits            ConstraintLimits
	metadata          RealizationNormalizationMetadata
	profiles          map[string]RealizationCollectionProfile
	optional, visited map[string]bool
	identities, nodes int
	failure           *RealizationConstraintBuildResult
}

func (n *literalNormalizer) fail(status, pointer, message string) {
	if n.failure == nil {
		result := normalizationFailure(status, pointer, message)
		n.failure = &result
	}
}
func (n *literalNormalizer) identity(pointer string) bool {
	n.identities++
	if n.identities > n.limits.MaxIdentityChecks {
		n.fail("limit-exceeded", pointer, "Profiled collection normalization exceeded max_identity_checks.")
		return false
	}
	return true
}

// NormalizeRealizationLiteral lowers bounded native values through the shared
// constraint owner. Source metadata never grants independent admission.
func NormalizeRealizationLiteral(input Fragment, semanticProfile string, defaultClosure RealizationClosure, metadata RealizationNormalizationMetadata, limits ConstraintLimits) (RealizationConstraintBuildResult, error) {
	if err := limits.Validate(); err != nil {
		return RealizationConstraintBuildResult{}, err
	}
	if err := CheckFragment(input, RealizationValue); err != nil {
		return RealizationConstraintBuildResult{}, err
	}
	n := literalNormalizer{limits: limits, metadata: metadata, profiles: map[string]RealizationCollectionProfile{}, optional: map[string]bool{}, visited: map[string]bool{}}
	result, err := n.admitMetadata(semanticProfile, defaultClosure)
	if err != nil {
		return RealizationConstraintBuildResult{}, err
	}
	if result != nil {
		return *result, nil
	}
	source := input.Document()
	if checkErr := value.Validate(source, limits.native()); checkErr != nil {
		return normalizationFailure("limit-exceeded", "", "Literal normalization exceeded admitted value bounds."), nil //nolint:nilerr // This relation reports candidate refusal in its result without failing the enclosing operation.
	}
	scopes := n.scopes(source)
	if n.failure != nil {
		return *n.failure, nil
	}
	root := n.node(source, "", "", 0)
	if n.failure != nil {
		return *n.failure, nil
	}
	if !normalizationPointersVisited(n.visited, metadata.LeafConstraints) || !normalizationPointersVisited(n.visited, n.optional) || !normalizationPointersVisited(n.visited, metadata.MemberPresence) {
		n.fail("invalid", "", "Normalization metadata does not resolve a source value.")
	}
	if n.failure != nil {
		return *n.failure, nil
	}
	document := map[string]any{termContractID: termRecursiveRealizationConstraintV1, termSemanticProfile: semanticProfile, termDefaultClosure: normalizationClosure(defaultClosure), "scopes": scopes, "root": root, "definitions": map[string]any{}}
	owner, err := normalizationOwner()
	if err != nil {
		return RealizationConstraintBuildResult{}, err
	}
	builtFragment, err := AdmitFragment(owner, RealizationConstraint, document, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 256})
	if err != nil {
		return normalizationFailure("invalid", "", "Normalization could not preserve the source authority."), nil //nolint:nilerr // This relation reports candidate refusal in its result without failing the enclosing operation.
	}
	owned, nativeErr := nativeFragment(builtFragment, RealizationConstraint)
	if nativeErr != nil {
		return RealizationConstraintBuildResult{}, nativeErr
	}
	var admitted constraintDocument
	decoder := json.NewDecoder(bytes.NewReader(owned.data))
	decoder.UseNumber()
	if err := decoder.Decode(&admitted); err != nil {
		return RealizationConstraintBuildResult{}, fragmentInvalid()
	}
	if !admitConstraintWork(admitted, document, limits) {
		return normalizationFailure("limit-exceeded", "", "Constraint admission exceeded bounded work limits."), nil
	}
	return RealizationConstraintBuildResult{Status: assuranceConformant, Document: builtFragment, Diagnostics: []diagnostic.Diagnostic{}}, nil
}

func normalizationPointersVisited[T any](visited map[string]bool, pointers map[string]T) bool {
	for pointer := range pointers {
		if !visited[pointer] {
			return false
		}
	}
	return true
}

func (n *literalNormalizer) node(input any, semanticPointer, sourcePointer string, depth int) map[string]any {
	n.nodes++
	if n.nodes > n.limits.MaxNodes || depth > n.limits.MaxDepth {
		n.fail("limit-exceeded", semanticPointer, "Literal normalization exceeded bounded work limits.")
		return nil
	}
	n.visited[sourcePointer] = true
	origin := n.metadata.Origins[sourcePointer]
	if origin == "" {
		origin = termAuthor
	}
	var node map[string]any
	if override, present := n.metadata.LeafConstraints[sourcePointer]; present {
		node = n.leafNode(input, override, semanticPointer)
	} else {
		node = n.contentNode(input, semanticPointer, sourcePointer, depth)
	}
	if node == nil {
		return nil
	}
	node[termOrigin] = origin
	if _, present := node[termPresence]; !present {
		node[termPresence] = requirementRequired
	}
	if n.optional[sourcePointer] {
		node[termPresence] = termOptional
	}
	if presence, present := n.metadata.MemberPresence[sourcePointer]; present {
		node[termPresence] = presence
	}
	return node
}

func (n *literalNormalizer) leafNode(input any, override Fragment, pointer string) map[string]any {
	_, object := input.(map[string]any)
	_, array := input.([]any)
	rule, ok := override.Document().(map[string]any)
	if object || array || !ok || !scalarNormalizationRule(rule) {
		n.fail("invalid", pointer, "A leaf constraint must address a scalar value.")
		return nil
	}
	return maps.Clone(rule)
}

func (n *literalNormalizer) contentNode(input any, semanticPointer, sourcePointer string, depth int) map[string]any {
	switch source := input.(type) {
	case map[string]any:
		return n.recordNode(source, semanticPointer, sourcePointer, depth)
	case []any:
		if profile, profiled := n.profiles[sourcePointer]; profiled {
			return n.keyedNode(source, profile, semanticPointer, sourcePointer, depth)
		}
		return n.sequenceNode(source, semanticPointer, sourcePointer, depth)
	default:
		return map[string]any{termKind: kindLiteral, "value": input}
	}
}

func (n *literalNormalizer) recordNode(source map[string]any, semanticPointer, sourcePointer string, depth int) map[string]any {
	fields := map[string]any{}
	for _, key := range slices.Sorted(maps.Keys(source)) {
		fields[key] = n.node(source[key], pointerAppend(semanticPointer, key), pointerAppend(sourcePointer, key), depth+1)
		if n.failure != nil {
			return nil
		}
	}
	return map[string]any{termKind: kindRecursiveRecord, "fields": fields, termClosure: normalizationClosure(RealizationClosure{})}
}

func (n *literalNormalizer) sequenceNode(source []any, semanticPointer, sourcePointer string, depth int) map[string]any {
	items := make([]any, 0, len(source))
	for index, child := range source {
		position := strconv.Itoa(index)
		built := n.node(child, pointerAppend(semanticPointer, position), pointerAppend(sourcePointer, position), depth+1)
		if n.failure != nil {
			return nil
		}
		items = append(items, built)
	}
	return map[string]any{termKind: termSequence, "items": items, termClosure: normalizationClosure(RealizationClosure{}), termMinItems: 0, termMaxItems: 4096}
}

func (n *literalNormalizer) keyedNode(source []any, profile RealizationCollectionProfile, semanticPointer, sourcePointer string, depth int) map[string]any {
	members := make([]any, 0, len(source))
	identities := map[string]bool{}
	for index, child := range source {
		position := strconv.Itoa(index)
		if !n.identity(semanticPointer) {
			return nil
		}
		identity, key, valid := normalizationIdentity(child, profile.IdentityFields)
		if !valid {
			n.fail("invalid", pointerAppend(semanticPointer, position), "A profiled collection member has no complete concrete semantic identity.")
			return nil
		}
		if identities[key] {
			n.fail("invalid", semanticPointer, "A profiled collection contains a duplicate semantic identity.")
			return nil
		}
		identities[key] = true
		built := n.node(child, pointerAppend(semanticPointer, "@"+key), pointerAppend(sourcePointer, position), depth+1)
		if n.failure != nil {
			return nil
		}
		members = append(members, map[string]any{termIdentity: identity, termConstraint: built})
	}
	return map[string]any{termKind: termKeyedCollection, termCollectionKind: profile.CollectionKind, termIdentityFields: stringInterfaces(profile.IdentityFields), "members": members, "aliases": []any{}, termClosure: normalizationClosure(profile.Closure), termMinItems: 0, termMaxItems: 4096}
}

func scalarNormalizationRule(rule map[string]any) bool {
	switch rule[termKind] {
	case kindLiteral, fieldDomain, "knowledge", termDelegated:
		return true
	case termAllOf:
		children, ok := rule["constraints"].([]any)
		if !ok || len(children) > 256 {
			return false
		}
		for _, child := range children {
			record, ok := child.(map[string]any)
			if !ok || record[termKind] == termAllOf || !scalarNormalizationRule(record) {
				return false
			}
		}
		return true
	default:
		return false
	}
}

func pointerAppend(pointer, token string) string {
	return pointer + jsonpointer.FromTokens([]string{token})
}

func normalizationIdentity(input any, fields []string) ([]any, string, bool) {
	record, ok := input.(map[string]any)
	if !ok {
		return nil, "", false
	}
	identity := make([]any, len(fields))
	for i, key := range fields {
		item, present := record[key]
		if !present {
			return nil, "", false
		}
		switch scalar := item.(type) {
		case string, bool:
		case json.Number:
			if strings.ContainsAny(string(scalar), ".eE") {
				return nil, "", false
			}
		default:
			return nil, "", false
		}
		identity[i] = item
	}
	key, err := jsonDigest(identity)
	return identity, key, err == nil
}

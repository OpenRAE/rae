package admission

import (
	"encoding/json"
	"math/big"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// Metadata work and semantic nodes have separate counters. Metadata comes
// from sealed models; scalar validity remains with the shared value owner.
type constraintAdmission struct {
	limits                                     ConstraintLimits
	nodes, operations, identities, scalarBytes int
	failure                                    *constraintResult
}
type constraintMetadataField struct {
	name  string
	value any
}
type constraintMetadata []constraintMetadataField

func (b *constraintAdmission) fail(pointer, message string) bool {
	result := constraintFailure("limit-exceeded", pointer, message)
	b.failure = &result
	return false
}
func constraintAdmissionPath(parent, child string) string {
	return parent + "/" + jsonpointer.EscapeToken(child)
}
func (b *constraintAdmission) metadata(input any) bool { return b.metadataAt(input, "", 0) }
func (b *constraintAdmission) metadataAt(input any, path string, depth int) bool {
	if depth > b.limits.MaxDepth {
		return b.fail(path, "Constraint metadata exceeded max_depth.")
	}
	b.operations++
	if b.operations > b.limits.MaxOperations {
		return b.fail(path, "Constraint metadata admission exceeded max_operations.")
	}
	switch item := input.(type) {
	case constraintMetadata:
		return b.metadataFields(item, path, depth)
	case map[string]any:
		return b.metadataFields(constraintMetadataObject(item), path, depth)
	case []any:
		return b.metadataSequence(item, path, depth)
	default:
		return b.metadataScalar(item, path)
	}
}
func (b *constraintAdmission) metadataScalar(input any, path string) bool {
	size := constraintScalarBytes(input)
	if size > b.limits.MaxScalarBytes {
		return b.fail(path, "Constraint metadata exceeded max_scalar_bytes.")
	}
	if value.Validate(input, constraintScalarLimits(b.limits)) != nil {
		return b.fail(path, "Constraint metadata exceeded invalid_utf8.")
	}
	b.scalarBytes += size
	if b.scalarBytes > b.limits.MaxTotalScalarBytes {
		return b.fail(path, "Constraint metadata exceeded max_total_scalar_bytes.")
	}
	return true
}
func constraintScalarLimits(limits ConstraintLimits) value.Limits {
	result := limits.native()
	// Aggregate charging belongs to the enclosing relation budget. A scalar
	// validity check must not misclassify aggregate exhaustion as invalid text.
	result.MaxTotalScalarBytes = max(result.MaxTotalScalarBytes, result.MaxScalarBytes)
	return result
}
func (b *constraintAdmission) metadataFields(fields constraintMetadata, path string, depth int) bool {
	if len(fields) > b.limits.MaxMembers {
		return b.fail(path, "Constraint metadata exceeded max_members.")
	}
	for _, field := range fields {
		child := constraintAdmissionPath(path, field.name)
		if !b.metadataAt(field.name, child+"/$key", depth+1) || !b.metadataAt(field.value, child, depth+1) {
			return false
		}
	}
	return true
}
func (b *constraintAdmission) metadataSequence(items []any, path string, depth int) bool {
	if len(items) > b.limits.MaxMembers {
		return b.fail(path, "Constraint metadata exceeded max_members.")
	}
	for index, child := range items {
		if !b.metadataAt(child, path+"/"+strconv.Itoa(index), depth+1) {
			return false
		}
	}
	return true
}
func constraintMetadataObject(input map[string]any) constraintMetadata {
	keys := make([]string, 0, len(input))
	for key := range input {
		keys = append(keys, key)
	}
	slices.Sort(keys)
	result := make(constraintMetadata, len(keys))
	for index, key := range keys {
		result[index] = constraintMetadataField{key, input[key]}
	}
	return result
}
func constraintScalarBytes(input any) int {
	switch scalar := input.(type) {
	case nil, bool:
		return 8
	case string:
		return len(scalar)
	case int:
		return max(1, (big.NewInt(int64(scalar)).BitLen()+7)/8)
	case int64:
		return max(1, (big.NewInt(scalar).BitLen()+7)/8)
	case json.Number:
		if strings.ContainsAny(string(scalar), ".eE") {
			return 8
		}
		integer, valid := new(big.Int).SetString(string(scalar), 10)
		if valid {
			return max(1, (integer.BitLen()+7)/8)
		}
	}
	return 0
}
func constraintClosureWorkMetadata(closure constraintClosure) constraintMetadata {
	posture := closure.Posture
	if posture == "" {
		posture = termUndefined
	}
	var universe, profile any
	if closure.Universe != "" {
		universe = closure.Universe
	}
	if closure.Profile != "" {
		profile = closure.Profile
	}
	return constraintMetadata{{"posture", posture}, {"universe", universe}, {termProfile, profile}}
}
func (b *constraintAdmission) node(node *constraintNode, path string, depth int) bool {
	b.nodes++
	b.operations++
	switch {
	case depth > b.limits.MaxDepth:
		return b.fail(path, "Constraint admission exceeded max_depth.")
	case b.nodes > b.limits.MaxNodes:
		return b.fail(path, "Constraint admission exceeded max_nodes.")
	case b.operations > b.limits.MaxOperations:
		return b.fail(path, "Constraint admission exceeded max_operations.")
	}
	presence, origin := node.Presence, node.Origin
	if presence == "" {
		presence = requirementRequired
	}
	if origin == "" {
		origin = termAuthor
	}
	if !b.metadataAt(constraintMetadata{{termKind, node.Kind}, {termPresence, presence}, {termOrigin, origin}}, path+"/$header", 0) {
		return false
	}
	return b.nodeContents(node, path, depth)
}
func (b *constraintAdmission) nodeContents(node *constraintNode, path string, depth int) bool {
	switch node.Kind {
	case kindLiteral:
		return b.metadataAt(node.Value, path+"/value", 0)
	case fieldDomain, termGraphReference:
		return b.metadataAt(constraintDomainMetadata(object(node.Domain)), path+"/domain", 0) && (node.Kind != termGraphReference || b.metadataAt(node.CyclePolicy, path+"/cycle_policy", 0))
	case "definition-reference":
		return b.metadataAt(node.Target, path+"/target", 0)
	case kindRecursiveRecord:
		return b.record(node, path, depth)
	case termSequence:
		return b.sequence(node, path, depth)
	case termKeyedCollection:
		return b.keyed(node, path, depth)
	case termAllOf:
		return b.children(node.Constraints, path, depth)
	}
	return true
}
func (b *constraintAdmission) record(node *constraintNode, path string, depth int) bool {
	if !b.metadataAt(constraintClosureWorkMetadata(node.Closure), path+"/closure", 0) {
		return false
	}
	if len(node.Fields) > b.limits.MaxMembers {
		return b.fail(path, "Constraint record exceeded max_members.")
	}
	for _, field := range node.Fields {
		child := constraintAdmissionPath(path, field.name)
		if !b.metadataAt(field.name, child+"/$key", 0) || !b.node(field.rule, child, depth+1) {
			return false
		}
	}
	return true
}
func (b *constraintAdmission) sequence(node *constraintNode, path string, depth int) bool {
	if !b.metadataAt(constraintClosureWorkMetadata(node.Closure), path+"/closure", 0) {
		return false
	}
	if !b.metadataAt(constraintMetadata{{termMinItems, node.MinItems}, {termMaxItems, constraintMaximum(node)}}, path+"/cardinality", 0) {
		return false
	}
	return b.children(node.Items, path, depth)
}
func constraintMaximum(node *constraintNode) int {
	if node.MaxItems != nil {
		return *node.MaxItems
	}
	return 4096
}
func (b *constraintAdmission) keyed(node *constraintNode, path string, depth int) bool {
	metadata := constraintMetadata{{termCollectionKind, node.CollectionKind}, {termIdentityFields, stringInterfaces(node.IdentityFields)}, {termClosure, constraintClosureWorkMetadata(node.Closure)}, {termMinItems, node.MinItems}, {termMaxItems, constraintMaximum(node)}}
	if !b.metadataAt(metadata, path+"/$collection", 0) || !b.aliases(node, path) {
		return false
	}
	for index, member := range node.Members {
		child := path + "/" + strconv.Itoa(index)
		if !b.identity(child) || !b.metadataAt(member.Identity, child+"/identity", 0) || !b.node(member.Constraint, child, depth+1) {
			return false
		}
	}
	return true
}
func (b *constraintAdmission) identity(path string) bool {
	b.identities++
	if b.identities > b.limits.MaxIdentityChecks {
		return b.fail(path, "Constraint admission exceeded max_identity_checks.")
	}
	return true
}
func (b *constraintAdmission) aliases(node *constraintNode, path string) bool {
	if len(node.Aliases) > b.limits.MaxMembers {
		return b.fail(path, "Constraint aliases exceeded max_members.")
	}
	for index, alias := range node.Aliases {
		child := path + "/aliases/" + strconv.Itoa(index)
		if !b.identity(child) || !b.metadataAt(constraintMetadata{{termIdentity, alias.Identity}, {termTarget, alias.Target}}, child, 0) {
			return false
		}
	}
	return true
}
func (b *constraintAdmission) children(children []*constraintNode, path string, depth int) bool {
	if len(children) > b.limits.MaxMembers {
		return b.fail(path, "Constraint children exceeded max_members.")
	}
	for index, child := range children {
		if !b.node(child, path+"/"+strconv.Itoa(index), depth+1) {
			return false
		}
	}
	return true
}
func admitConstraintWork(document constraintDocument, source map[string]any, limits ConstraintLimits) bool {
	return constraintWorkFailure(document, source, limits) == nil
}
func constraintWorkFailure(document constraintDocument, source map[string]any, limits ConstraintLimits) *constraintResult {
	budget := constraintAdmission{limits: limits}
	header := constraintMetadata{{termContractID, termRecursiveRealizationConstraintV1}, {termSemanticProfile, source[termSemanticProfile]}, {termDefaultClosure, constraintClosureWorkMetadata(document.DefaultClosure)}}
	if !budget.metadataAt(header, "/$document", 0) || !budget.scopes(document.Scopes) || !budget.node(document.Root, "/root", 0) {
		return budget.failure
	}
	for _, definition := range document.Definitions {
		child := constraintAdmissionPath("/definitions", definition.name)
		if !budget.metadataAt(definition.name, child+"/$key", 0) || !budget.node(definition.rule, child, 0) {
			return budget.failure
		}
	}
	return nil
}
func (b *constraintAdmission) scopes(scopes []constraintScope) bool {
	if len(scopes) > b.limits.MaxMembers {
		return b.fail("/scopes", "Constraint scopes exceeded max_members.")
	}
	for index, scope := range scopes {
		origin := scope.Origin
		if origin == "" {
			origin = termAuthor
		}
		metadata := constraintMetadata{{termFieldPointer, scope.Pointer}, {termClosure, constraintClosureWorkMetadata(scope.Closure)}, {termOrigin, origin}}
		if !b.metadataAt(metadata, "/scopes/"+strconv.Itoa(index), 0) {
			return false
		}
	}
	return true
}

// This closed metadata view follows the existing domain models' field order
// and defaults. It does not parse or admit a second domain language.
func constraintDomainMetadata(input map[string]any) constraintMetadata {
	kind := stringAt(input, termKind)
	result := constraintMetadata{{termKind, kind}}
	fields := []string{}
	switch kind {
	case "exact", "boolean":
		fields = []string{termValue}
	case "enum":
		fields = []string{"values"}
	case "numeric-interval":
		fields = []string{"numeric_type", "lower", "upper", termLowerClosed, termUpperClosed}
	case "governed-reference":
		fields = []string{termAuthority, "allowed_refs"}
	case "record":
		fields = []string{"fields", "extra"}
	case termVersion:
		fields = []string{termRelation, "lower", "upper", termLowerClosed, termUpperClosed}
	}
	for _, name := range fields {
		entry, present := input[name]
		if !present && (name == termLowerClosed || name == termUpperClosed) {
			entry = true
		} else if !present && name == "extra" {
			entry = false
		}
		if name == termRelation {
			relation := object(entry)
			entry = constraintMetadata{{termAuthority, relation[termAuthority]}, {termContractID, relation[termContractID]}, {"revision", relation["revision"]}, {termDigest, relation[termDigest]}}
		}
		result = append(result, constraintMetadataField{name, entry})
	}
	return result
}

func constraintClosureMetadata(closure constraintClosure) map[string]any {
	result := map[string]any{}
	for _, field := range constraintClosureWorkMetadata(closure) {
		result[field.name] = field.value
	}
	return result
}

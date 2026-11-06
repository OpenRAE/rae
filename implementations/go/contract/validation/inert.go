package validation

import (
	"maps"
	"slices"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

const inertDialect = "https://json-schema.org/draft/2020-12/schema"

// InertLimits bounds each input inspection and the shared schema/value work.
// Limits must be positive, except MaxReferences which may be zero.
type InertLimits struct{ MaxBytes, MaxDepth, MaxNodes, MaxScalarBytes, MaxReferences, MaxEvaluations int }

// CheckInertSchema checks a caller-supplied profile without retrieval or code
// execution. Only the reference profile's safe keyword subset is admitted.
// Caller resource identities never enter the trusted meta-schema registry.
func CheckInertSchema(schemaJSON, valueJSON []byte, supportedKeywords []string, limits InertLimits) error {
	if !validInertLimits(limits) {
		return inertFailure()
	}
	schema, err := readInert(schemaJSON, limits)
	if err != nil {
		return err
	}
	root, ok := schema.value.(map[string]any)
	if !ok {
		return inertFailure()
	}
	value, err := readInert(valueJSON, limits)
	if err != nil {
		return err
	}
	walk := inertInspection{limits: limits, supported: supportedKeywords, root: schema}
	if !walk.schema(schema, 0, map[string]bool{}) || walk.nodes > limits.MaxEvaluations/value.nodes {
		return inertFailure()
	}
	engine := inertEvaluator{remaining: limits.MaxEvaluations, root: schema, atoms: map[*inertNode]map[string]*jsonschema.Schema{}}
	if !engine.meta(schema.value) || !engine.check(schema, value, true) || engine.err != nil || !checkCompleteInertSchema(root, value.value) {
		return inertFailure()
	}
	return nil
}

func validInertLimits(l InertLimits) bool {
	return l.MaxBytes > 0 && l.MaxBytes <= 16777216 && l.MaxDepth > 0 && l.MaxDepth <= 64 && l.MaxNodes > 0 && l.MaxNodes <= 65536 && l.MaxScalarBytes > 0 && l.MaxScalarBytes <= 16777216 && l.MaxReferences >= 0 && l.MaxReferences <= 4096 && l.MaxEvaluations > 0 && l.MaxEvaluations <= 1048576
}
func inertFailure() error { return failure(fault.InvalidInput, "contract-profile-invalid") }
func inertSafeKeywords() []string {
	return []string{"$anchor", "$comment", keywordDefs, "$id", keywordRef, keywordSchema, "$vocabulary", keywordAdditionalProperties, keywordAllOf, keywordAnyOf, keywordConst, keywordContains, "default", "dependentRequired", keywordDependentSchemas, "deprecated", "description", keywordElse, keywordEnum, "examples", "exclusiveMaximum", "exclusiveMinimum", "if", keywordItems, "maxContains", "maxItems", "maxLength", "maxProperties", "maximum", "minContains", "minItems", "minLength", "minProperties", "minimum", "multipleOf", keywordNot, keywordOneOf, keywordPrefixItems, keywordProperties, keywordPropertyNames, "readOnly", keywordRequired, keywordThen, "title", keywordType, "writeOnly"}
}

type inertInspection struct {
	limits            InertLimits
	supported         []string
	root              *inertNode
	nodes, references int
}

func (i *inertInspection) schema(n *inertNode, depth int, active map[string]bool) bool {
	i.nodes++
	if i.nodes > i.limits.MaxNodes || depth > i.limits.MaxDepth {
		return false
	}
	if _, ok := n.value.(bool); ok {
		return true
	}
	if _, ok := n.value.(map[string]any); !ok {
		return false
	}
	if n != i.root && (n.members["$id"] != nil || n.members[keywordSchema] != nil) {
		return false
	}
	for _, k := range n.keys {
		child := n.members[k]
		if !slices.Contains(inertSafeKeywords(), k) || !slices.Contains(i.supported, k) {
			return false
		}
		if !i.child(k, child, depth, active) {
			return false
		}
	}
	return true
}
func (i *inertInspection) child(k string, n *inertNode, depth int, active map[string]bool) bool {
	switch k {
	case keywordConst:
		return inertScalar(n.value)
	case keywordEnum:
		for _, v := range n.items {
			if !inertScalar(v.value) {
				return false
			}
		}
	case keywordRef:
		return i.reference(n, depth, active)
	case keywordDefs, keywordDependentSchemas, keywordProperties:
		return i.children(n, depth, active, true)
	case keywordAllOf, keywordAnyOf, keywordOneOf, keywordPrefixItems:
		return i.children(n, depth, active, false)
	case keywordAdditionalProperties, keywordContains, keywordElse, "if", keywordItems, keywordNot, keywordPropertyNames, keywordThen:
		return i.schema(n, depth+1, active)
	}
	return true
}
func (i *inertInspection) children(n *inertNode, depth int, active map[string]bool, object bool) bool {
	children := n.items
	if object {
		if _, ok := n.value.(map[string]any); !ok {
			return false
		}
		children = make([]*inertNode, 0, len(n.keys))
		for _, key := range n.keys {
			children = append(children, n.members[key])
		}
	} else {
		if _, ok := n.value.([]any); !ok {
			return false
		}
	}
	for _, child := range children {
		if !i.schema(child, depth+1, active) {
			return false
		}
	}
	return true
}
func (i *inertInspection) reference(n *inertNode, depth int, active map[string]bool) bool {
	ref, ok := n.value.(string)
	if !ok || active[ref] {
		return false
	}
	i.references++
	if i.references > i.limits.MaxReferences {
		return false
	}
	target := inertPointer(i.root, ref)
	if target == nil {
		return false
	}
	active[ref] = true
	valid := i.schema(target, depth+1, active)
	delete(active, ref)
	return valid
}
func inertScalar(v any) bool {
	switch v.(type) {
	case map[string]any, []any:
		return false
	}
	return true
}

// The pinned schema engine owns the trusted standard meta-schema registry.
// Python's root META_SCHEMA traverses these seven resources in this order.
func inertMeta() ([]*jsonschema.Schema, error) {
	c := inertCompiler(true)
	var result []*jsonschema.Schema
	for _, name := range []string{"core", "applicator", "unevaluated", "validation", "meta-data", "format-annotation", "content"} {
		s, err := c.Compile("https://json-schema.org/draft/2020-12/meta/" + name)
		if err != nil {
			return nil, err
		}
		result = append(result, s)
	}
	return result, nil
}

func inertCompiler(formats bool) *jsonschema.Compiler {
	c := jsonschema.NewCompiler()
	c.DefaultDraft(jsonschema.Draft2020)
	c.UseLoader(offline{})
	c.UseRegexpEngine(compilePattern)
	if formats {
		c.AssertFormat()
	}
	return c
}

func (e *inertEvaluator) meta(value any) bool {
	schemas, err := inertMeta()
	if err != nil {
		e.err = err
		return false
	}
	if !e.consume(1) {
		return false
	} // allOf in the reference's root META_SCHEMA.
	for _, s := range schemas {
		if !e.consume(1) || s.Validate(value) != nil {
			return false
		}
	}
	// Referenced resources declare $schema. Python evolves to the standard
	// validator there; their descendants are validated without budget wrappers.
	// The remaining wrapped root callbacks are type and properties. Safe caller
	// schemas cannot contain the deprecated members in root properties.
	return e.consume(2)
}

// The work trace does not grant schema validity. Use the maintained engine for
// the complete verdict, under a private identity. All admitted refs are local
// pointers and nested resource identities were refused during inspection.
func checkCompleteInertSchema(schema map[string]any, value any) bool {
	document := maps.Clone(schema)
	const location = "urn:raes:private-profile-complete"
	document["$id"] = location
	compiler := inertCompiler(false)
	if err := compiler.AddResource(location, document); err != nil {
		return false
	}
	compiled, err := compiler.Compile(location)
	return err == nil && compiled.Validate(value) == nil
}

package validation

import (
	"encoding/json"
	"slices"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

type inertEvaluator struct {
	remaining int
	root      *inertNode
	atoms     map[*inertNode]map[string]*jsonschema.Schema
	err       error
}

func (e *inertEvaluator) consume(cost int) bool {
	if e.err != nil {
		return false
	}
	e.remaining -= cost
	if e.remaining < 0 {
		e.err = inertOutcome(InertLimitExceeded)
		return false
	}
	return true
}

// failure returns the recorded evaluator error, or the outcome of the check.
func (e *inertEvaluator) failure(code string) error {
	if e.err != nil {
		return e.err
	}
	return inertOutcome(code)
}
func (e *inertEvaluator) check(schema, value *inertNode, first bool) bool {
	if e.err != nil || schema == nil {
		return false
	}
	if flag, ok := schema.value.(bool); ok {
		return flag
	}
	valid := true
	for _, key := range schema.keys {
		if !inertValidationKeyword(key) {
			continue
		}
		if !e.consume(inertKeywordCost(key, schema.members[key].value, value.value)) {
			return false
		}
		if !e.keyword(schema, key, value, first) {
			valid = false
			if first {
				return false
			}
		}
	}
	return valid && e.err == nil
}
func inertValidationKeyword(key string) bool {
	return slices.Contains([]string{keywordRef, keywordAdditionalProperties, keywordAllOf, keywordAnyOf, keywordConst, keywordContains, "dependentRequired", keywordDependentSchemas, keywordEnum, "exclusiveMaximum", "exclusiveMinimum", "if", keywordItems, "maxItems", keywordMaxLength, "maxProperties", "maximum", "minItems", keywordMinLength, "minProperties", "minimum", "multipleOf", keywordNot, keywordOneOf, keywordPrefixItems, keywordProperties, keywordPropertyNames, keywordRequired, keywordType}, key)
}
func (e *inertEvaluator) keyword(schema *inertNode, key string, value *inertNode, first bool) bool {
	child := schema.members[key]
	switch key {
	case keywordRef:
		ref, _ := child.value.(string)
		return e.check(inertPointer(e.root, ref), value, first)
	case keywordAllOf, keywordAnyOf, keywordOneOf:
		return e.combination(key, child, value, first)
	case keywordNot:
		return !e.check(child, value, true)
	case "if":
		branch := keywordElse
		if e.check(child, value, true) {
			branch = keywordThen
		}
		if next := schema.members[branch]; next != nil {
			return e.check(next, value, first)
		}
		return true
	case keywordProperties, keywordPropertyNames, keywordAdditionalProperties, keywordDependentSchemas:
		return e.object(schema, key, value, first)
	case keywordItems, keywordPrefixItems, keywordContains:
		return e.array(schema, key, value, first)
	default:
		return e.atomic(schema, key, value.value)
	}
}
func (e *inertEvaluator) combination(key string, children, value *inertNode, first bool) bool {
	if key == keywordOneOf {
		return e.exactlyOne(children, value)
	}
	valid := key == keywordAllOf
	for _, child := range children.items {
		accepted := e.check(child, value, first && key == keywordAllOf)
		if e.err != nil {
			return false
		}
		if key == keywordAnyOf && accepted {
			return true
		}
		if key == keywordAllOf && !accepted {
			valid = false
			if first {
				return false
			}
		}
	}
	return valid
}
func (e *inertEvaluator) exactlyOne(children, value *inertNode) bool {
	matches := 0
	for _, child := range children.items {
		if e.check(child, value, matches > 0) {
			matches++
		}
		if e.err != nil {
			return false
		}
	}
	return matches == 1
}
func (e *inertEvaluator) atomic(schema *inertNode, key string, value any) bool {
	cached := e.atoms[schema]
	if cached == nil {
		cached = map[string]*jsonschema.Schema{}
		e.atoms[schema] = cached
	}
	compiled := cached[key]
	if compiled == nil {
		c := inertCompiler(false)
		doc := map[string]any{keywordSchema: inertDialect, key: schema.members[key].value}
		location := "urn:raes:private-profile-assertion"
		if err := c.AddResource(location, doc); err != nil {
			e.err = inertOutcome(InertSchemaInvalid)
			return false
		}
		var err error
		compiled, err = c.Compile(location)
		if err != nil {
			e.err = inertOutcome(InertSchemaInvalid)
			return false
		}
		cached[key] = compiled
	}
	return compiled.Validate(value) == nil
}
func inertInt(schema *inertNode, key string, fallback int) int {
	child := schema.members[key]
	if child == nil {
		return fallback
	}
	n, ok := child.value.(json.Number)
	if !ok {
		return fallback
	}
	f, err := n.Float64()
	if err != nil || f > 1048576 {
		return 1048577
	}
	return int(f)
}

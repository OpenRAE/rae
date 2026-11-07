package authoring

import (
	"encoding/json"
	"errors"
	"maps"
	"regexp"
	"slices"
	"sort"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type field struct {
	name  string
	value any
	omit  bool
}
type ordered []field

type normalizer struct {
	parser    *Parser
	id        string
	ranges    map[string]source.Range
	remaining int
	patterns  map[string]*regexp.Regexp
}

func resolve(root map[string]any, pointer string) map[string]any {
	var current any = root
	if pointer == "#" {
		return root
	}
	for _, token := range jsonpointer.Tokens(strings.TrimPrefix(pointer, "#")) {
		current = object(current)[token]
	}
	return object(current)
}
func (w *normalizer) dereference(schema map[string]any, pointer string) (map[string]any, string) {
	for i := 0; i < 16; i++ {
		ref := text(schema["$ref"])
		if ref == "" {
			return schema, pointer
		}
		pointer = ref
		schema = resolve(w.parser.schemas[w.id], ref)
	}
	return nil, pointer
}
func (w *normalizer) walk(schema map[string]any, pointer string, value any, path string, policy scalarPolicy) (result any, failure error) {
	defer func() { failure = locatedModelError(failure, path) }()
	w.remaining--
	if w.remaining < 0 || strings.Count(path, "/") > w.parser.limits.MaxDepth {
		return nil, invalid()
	}
	schema, pointer = w.dereference(schema, pointer)
	if schema == nil {
		schema = map[string]any{}
	}
	value = packageShorthand(pointer, value)
	value, err := w.convert(schema, value, policy)
	if err != nil {
		return nil, err
	}
	if chosen, selected := w.choose(alternatives(schema), value); chosen != nil {
		policy.Convert = nil
		return w.walk(chosen, selected, value, path, policy)
	}
	return w.walkValue(schema, pointer, value, path, policy)
}
func locatedModelError(err error, path string) error {
	if err == nil {
		return nil
	}
	if _, ok := errors.AsType[*modelError](err); ok {
		return err
	}
	return &modelError{path: path, cause: err}
}
func packageShorthand(pointer string, value any) any {
	if pointer == "#/$defs/Source" {
		if s, ok := value.(string); ok {
			return map[string]any{"name": s, "version": "*"}
		}
	}
	return value
}
func (w *normalizer) walkValue(schema map[string]any, pointer string, value any, path string, policy scalarPolicy) (any, error) {
	switch v := value.(type) {
	case map[string]any:
		return w.mapping(schema, pointer, v, path, policy)
	case []any:
		return w.sequence(schema, pointer, v, path, policy)
	default:
		return value, nil
	}
}
func (w *normalizer) sequence(schema map[string]any, pointer string, items []any, path string, policy scalarPolicy) (any, error) {
	result := make([]any, len(items))
	for i, item := range items {
		child := object(schema["items"])
		if positional := array(schema["prefixItems"]); i < len(positional) {
			child = object(positional[i])
		}
		value, err := w.walk(child, pointer+"/items", item, path+"/"+strconv.Itoa(i), childPolicy(policy.Items))
		if err != nil {
			return nil, err
		}
		result[i] = value
	}
	return result, nil
}
func alternatives(schema map[string]any) []any {
	if branches := array(schema["anyOf"]); len(branches) > 0 {
		return branches
	}
	return array(schema["oneOf"])
}
func (w *normalizer) choose(branches []any, value any) (map[string]any, string) {
	for _, item := range branches {
		schema, pointer := w.dereference(object(item), "")
		_, isString := value.(string)
		if schemaMatches(schema, value) || pointer == "#/$defs/Source" && isString {
			return object(item), pointer
		}
	}
	return nil, ""
}
func schemaMatches(schema map[string]any, value any) bool {
	if c, has := schema["const"]; has && c != value {
		return false
	}
	switch v := value.(type) {
	case map[string]any:
		if text(schema["type"]) != "object" && schema["properties"] == nil {
			return false
		}
		for _, required := range array(schema["required"]) {
			if _, ok := v[text(required)]; !ok {
				return false
			}
		}
		for name, raw := range object(schema["properties"]) {
			if expected, present := object(raw)["const"]; present && v[name] != expected {
				return false
			}
		}
		return true
	case []any:
		return schema["type"] == "array"
	case string:
		return schema["type"] == "string" || schema["enum"] != nil
	case bool:
		return schema["type"] == "boolean"
	case float64:
		return schema["type"] == "number" || schema["type"] == "integer"
	case json.Number:
		return schema["type"] == "number" || schema["type"] == "integer"
	case nil:
		return schema["type"] == "null"
	default:
		return len(schema) == 0
	}
}
func (w *normalizer) mapping(schema map[string]any, pointer string, value map[string]any, path string, policy scalarPolicy) (any, error) {
	presentation := w.parser.layouts[w.id][pointer]
	keys := fieldOrder(w.keys(value, path), presentation.Fields)
	result := make(ordered, 0, len(value))
	for _, name := range keys {
		child, err := w.propertySchema(schema, name)
		if err != nil {
			return nil, err
		}
		raw, err := w.fieldInput(pointer, name, value[name])
		if err != nil {
			return nil, err
		}
		fieldPolicy, present := presentation.Scalar[name]
		if !present {
			fieldPolicy = childPolicy(policy.Values)
		}
		normalized, err := w.walk(child, pointer+"/properties/"+name, raw, path+"/"+jsonpointer.EscapeToken(name), fieldPolicy)
		if err != nil {
			return nil, err
		}
		result = append(result, field{name: name, value: normalized, omit: omitted(normalized, presentation.Omit[name])})
	}
	if err := w.modelCheck(pointer, object(result)); err != nil {
		return nil, err
	}
	return result, nil
}
func (w *normalizer) propertySchema(schema map[string]any, name string) (map[string]any, error) {
	if child, present := object(schema["properties"])[name]; present {
		return object(child), nil
	}
	patterns := object(schema["patternProperties"])
	for _, pattern := range slices.Sorted(maps.Keys(patterns)) {
		compiled, err := w.propertyPattern(pattern)
		if err != nil {
			return nil, err
		}
		if compiled.MatchString(name) {
			return object(patterns[pattern]), nil
		}
	}
	return object(schema["additionalProperties"]), nil
}
func (w *normalizer) propertyPattern(pattern string) (*regexp.Regexp, error) {
	if w.patterns == nil {
		w.patterns = map[string]*regexp.Regexp{}
	}
	if compiled := w.patterns[pattern]; compiled != nil {
		return compiled, nil
	}
	compiled, err := regexp.Compile(pattern)
	if err != nil {
		return nil, err
	}
	w.patterns[pattern] = compiled
	return compiled, nil
}
func (w *normalizer) keys(value map[string]any, path string) []string {
	keys := slices.Sorted(maps.Keys(value))
	sort.SliceStable(keys, func(i, j int) bool {
		left, l := w.ranges[path+"/"+jsonpointer.EscapeToken(keys[i])]
		right, r := w.ranges[path+"/"+jsonpointer.EscapeToken(keys[j])]
		if l != r {
			return l
		}
		if left.Start.Line != right.Start.Line {
			return left.Start.Line < right.Start.Line
		}
		return left.Start.Column < right.Start.Column
	})
	return keys
}
func fieldOrder(keys, fields []string) []string {
	result := make([]string, 0, len(keys))
	for _, f := range fields {
		if slices.Contains(keys, f) {
			result = append(result, f)
		}
	}
	for _, key := range keys {
		if !slices.Contains(result, key) {
			result = append(result, key)
		}
	}
	return result
}
func omitted(value any, policies []string) bool {
	return slices.ContainsFunc(policies, func(policy string) bool { return omitValue(value, policy) })
}
func omitValue(value any, policy string) bool {
	switch policy {
	case "always":
		return true
	case "null":
		return value == nil
	case "empty":
		v, ok := value.(ordered)
		return ok && len(v) == 0
	case "empty-sequence":
		v, ok := value.([]any)
		return ok && len(v) == 0
	case "blank":
		v, ok := value.(string)
		return ok && v == ""
	case "false":
		v, ok := value.(bool)
		return ok && !v
	default:
		return false
	}
}

type modelError struct {
	path  string
	cause error
}

func (e *modelError) Error() string { return "sdl model rejected" }
func (e *modelError) Unwrap() error { return e.cause }

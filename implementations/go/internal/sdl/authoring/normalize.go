package authoring

import (
	"encoding/json"
	"errors"
	"maps"
	"regexp"
	"slices"
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
	parser   *Parser
	id       string
	hints    map[string][]string
	patterns map[string]*regexp.Regexp
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
	for range 16 {
		ref := text(schema["$ref"])
		if ref == "" {
			return schema, pointer
		}
		pointer = ref
		schema = resolve(w.parser.schemas[w.id], ref)
	}
	return nil, pointer
}
func (w *normalizer) walk(schema map[string]any, pointer string, value any, path []string, policy scalarPolicy, view source.View) (result any, failure error) {
	defer func() { failure = locatedModelError(failure, path) }()
	schema, pointer = w.dereference(schema, pointer)
	if schema == nil {
		schema = map[string]any{}
	}
	value = packageShorthand(pointer, value)
	value, err := w.convert(schema, value, policy)
	if err != nil {
		return nil, err
	}
	if schema["type"] == stringType {
		if _, ok := value.(string); !ok {
			return nil, invalid()
		}
	}
	if chosen, selected := w.choose(alternatives(schema), value); chosen != nil {
		policy.Convert = nil
		return w.walk(chosen, selected, value, path, policy, view)
	}
	return w.walkValue(schema, pointer, value, path, policy, view)
}
func locatedModelError(err error, path []string) error {
	if err == nil {
		return nil
	}
	if _, ok := errors.AsType[*modelError](err); ok {
		return err
	}
	return &modelError{path: jsonpointer.FromTokens(path), cause: err}
}
func packageShorthand(pointer string, value any) any {
	if pointer == "#/$defs/Source" {
		if s, ok := value.(string); ok {
			return map[string]any{nameField: s, "version": "*"}
		}
	}
	return value
}
func (w *normalizer) walkValue(schema map[string]any, pointer string, value any, path []string, policy scalarPolicy, view source.View) (any, error) {
	switch v := value.(type) {
	case map[string]any:
		return w.mapping(schema, pointer, v, path, policy, view)
	case []any:
		return w.sequence(schema, pointer, v, path, policy, view)
	default:
		return value, nil
	}
}
func (w *normalizer) sequence(schema map[string]any, pointer string, items []any, path []string, policy scalarPolicy, view source.View) (any, error) {
	result := make([]any, len(items))
	for i, item := range items {
		child := object(schema["items"])
		if positional := array(schema["prefixItems"]); i < len(positional) {
			child = object(positional[i])
		}
		value, err := w.walk(child, pointer+"/items", item, appendPath(path, strconv.Itoa(i)), childPolicy(policy.Items), view.Child(strconv.Itoa(i)))
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
		return objectMatches(schema, v)
	case []any:
		return schema["type"] == "array"
	case string:
		return schema["type"] == stringType || schema["enum"] != nil
	case bool:
		return schema["type"] == booleanType
	case float64:
		return schema["type"] == numberType || schema["type"] == integerType
	case json.Number:
		return schema["type"] == numberType || schema["type"] == integerType
	case nil:
		return schema["type"] == nullType
	default:
		return len(schema) == 0
	}
}
func objectMatches(schema, value map[string]any) bool {
	if text(schema["type"]) != "object" && schema["properties"] == nil {
		return false
	}
	for _, required := range array(schema["required"]) {
		if _, ok := value[text(required)]; !ok {
			return false
		}
	}
	for name, raw := range object(schema["properties"]) {
		if expected, present := object(raw)["const"]; present && value[name] != expected {
			return false
		}
	}
	return true
}
func (w *normalizer) mapping(schema map[string]any, pointer string, value map[string]any, path []string, policy scalarPolicy, view source.View) (any, error) {
	presentation := w.parser.layoutFor(w.id, pointer)
	keys := fieldOrder(w.keys(value, path, view), presentation.Fields)
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
		childPointer := pointer + "/additionalProperties"
		if _, known := object(schema["properties"])[name]; known {
			childPointer = pointer + "/properties/" + jsonpointer.EscapeToken(name)
		}
		normalized, err := w.walk(child, childPointer, raw, appendPath(path, name), fieldPolicy, view.Child(name))
		if err != nil {
			return nil, err
		}
		normalized = omitInferredTarget(pointer, name, value[name], normalized)
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
	if schema["additionalProperties"] == false {
		return nil, invalid()
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
func (w *normalizer) keys(value map[string]any, path []string, view source.View) []string {
	known := view.Keys()
	if known == nil && nodeListPath(path) {
		known = w.hints[jsonpointer.FromTokens(path)]
	}
	keys := make([]string, 0, len(value))
	for _, name := range known {
		if _, present := value[name]; present {
			keys = append(keys, name)
		}
	}
	if len(keys) == len(value) {
		return keys
	}
	seen := map[string]bool{}
	for _, key := range keys {
		seen[key] = true
	}
	for _, key := range slices.Sorted(maps.Keys(value)) {
		if !seen[key] {
			keys = append(keys, key)
		}
	}
	return keys
}
func nodeListPath(path []string) bool {
	return len(path) == 3 && path[0] == nodesSection && slices.Contains([]string{featuresSection, conditionsSection, injectsSection}, path[2])
}
func fieldOrder(keys, fields []string) []string {
	if len(fields) == 0 {
		return keys
	}
	remaining := make(map[string]bool, len(keys))
	for _, key := range keys {
		remaining[key] = true
	}
	result := make([]string, 0, len(keys))
	for _, name := range fields {
		if remaining[name] {
			result = append(result, name)
			delete(remaining, name)
		}
	}
	for _, name := range keys {
		if remaining[name] {
			result = append(result, name)
		}
	}
	return result
}
func appendPath(path []string, token string) []string { return append(slices.Clone(path), token) }
func omitted(value any, policies []string) bool {
	return slices.ContainsFunc(policies, func(policy string) bool { return omitValue(value, policy) })
}
func omitValue(value any, policy string) bool {
	switch policy {
	case "always":
		return true
	case nullType:
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

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
	parser                        *Parser
	id                            string
	hints                         map[string][]string
	order                         map[string][]string
	patterns                      map[string]*regexp.Regexp
	workingLimit, scalarRemaining int64
	scalars                       map[string]string
	fields                        map[fieldValueKey]any
	casing                        map[textValueKey]string
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
			if model, selected := w.intersectionModel(schema); model != nil {
				return model, selected
			}
			return schema, pointer
		}
		pointer = ref
		schema = resolve(w.parser.schemas[w.id], ref)
	}
	return nil, pointer
}

func (w *normalizer) intersectionModel(schema map[string]any) (map[string]any, string) {
	if schema["properties"] != nil {
		return nil, ""
	}
	var selected map[string]any
	pointer := ""
	for _, raw := range array(schema["allOf"]) {
		reference := text(object(raw)["$ref"])
		if reference == "" || len(w.parser.layoutFor(w.id, reference).Fields) == 0 {
			continue
		}
		model := resolve(w.parser.schemas[w.id], reference)
		if model["properties"] == nil {
			continue
		}
		if selected != nil {
			return nil, ""
		}
		selected, pointer = model, reference
	}
	return selected, pointer
}
func (w *normalizer) walk(schema map[string]any, pointer string, value any, path []string, policy scalarPolicy, view source.View) (result any, failure error) {
	discriminator := modelDiscriminator(schema, value)
	defer func() {
		if failure == nil {
			result, failure = w.shareScalar(result)
		}
		failure = locatedModelError(failure, path)
		if failure != nil && discriminator != "" {
			failure = &modelError{cause: failure, causes: []error{failure}, discriminator: discriminator, discriminatorPath: jsonpointer.FromTokens(path)}
		}
	}()
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
	if schema["properties"] == nil {
		if chosen, selected := w.choose(alternatives(schema), value); chosen != nil {
			policy.Convert = nil
			return w.walk(chosen, selected, value, path, policy, view)
		}
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
	return w.chooseBranches(branches, value, 0)
}
func (w *normalizer) chooseBranches(branches []any, value any, depth int) (map[string]any, string) {
	if depth >= 16 {
		return nil, ""
	}
	for _, item := range branches {
		schema, pointer := w.dereference(object(item), "")
		if schema["properties"] == nil {
			if nested, selected := w.chooseBranches(alternatives(schema), value, depth+1); nested != nil {
				return nested, selected
			}
		}
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
	if text(schema["type"]) != termObject && schema["properties"] == nil {
		return false
	}
	for _, required := range array(schema["required"]) {
		if _, ok := value[text(required)]; !ok {
			return false
		}
	}
	for name, raw := range object(schema["properties"]) {
		actual, supplied := value[name]
		if expected, present := object(raw)["const"]; supplied && present && actual != expected {
			return false
		}
	}
	return true
}
func (w *normalizer) mapping(schema map[string]any, pointer string, value map[string]any, path []string, policy scalarPolicy, view source.View) (any, error) {
	value = w.contentConstructorInput(pointer, value)
	if pointer == "#/$defs/DomainProfileSchemaModel" && value["schema_digest"] == nil {
		value = maps.Clone(value)
		delete(value, "schema_digest")
	}
	presentation := w.parser.layoutFor(w.id, pointer)
	keys := fieldOrder(w.keys(value, path, view), presentation.Fields)
	result := make(ordered, 0, len(value))
	failures := []error{}
	for _, required := range array(schema["required"]) {
		name := text(required)
		if _, present := value[name]; !present {
			failures = append(failures, locatedModelError(invalid(), appendPath(path, name)))
		}
	}
	for _, name := range keys {
		normalized, err := w.mappingField(schema, pointer, value, name, path, policy, view, presentation)
		if err != nil {
			failures = append(failures, err)
			continue
		}
		result = append(result, normalized)
	}
	if len(failures) > 0 {
		return nil, &modelError{causes: failures, cause: invalid()}
	}
	result = modelOutput(pointer, result, presentation.Fields)
	result, err := w.profileSchemaOutput(pointer, result, presentation.Fields)
	if err != nil {
		return nil, err
	}
	if err := w.modelCheck(pointer, object(result)); err != nil {
		return nil, err
	}
	return result, nil
}

func (w *normalizer) mappingField(schema map[string]any, pointer string, value map[string]any, name string, path []string, policy scalarPolicy, view source.View, presentation layout) (field, error) {
	child, err := w.propertySchema(schema, name)
	if err != nil {
		return field{}, locatedModelError(err, appendPath(path, name))
	}
	raw, err := w.memoField(pointer, name, value[name])
	if err != nil {
		return field{}, locatedModelError(err, appendPath(path, name))
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
		return field{}, err
	}
	normalized = omitInferredTarget(pointer, name, value[name], normalized)
	return field{name: name, value: normalized, omit: omitted(normalized, presentation.Omit[name])}, nil
}

// The legacy service discriminator is supplied by the Content constructor,
// before union selection. Profile bindings never receive a service default.
func (w *normalizer) contentConstructorInput(pointer string, value map[string]any) map[string]any {
	if pointer != "#/$defs/Content" {
		return value
	}
	binding, mapping := value["service_materialization"].(map[string]any)
	if !mapping {
		return value
	}
	if _, supplied := binding["interface_profile"]; supplied {
		return value
	}
	if _, legacy := binding["target_service_ref"]; !legacy {
		return value
	}
	profile := resolve(w.parser.schemas[w.id], "#/$defs/DomainProfileBindingModel")
	for name := range object(profile["properties"]) {
		if _, supplied := binding[name]; supplied {
			return value
		}
	}
	result, service := maps.Clone(value), maps.Clone(binding)
	service["interface_profile"] = "service-content"
	result["service_materialization"] = service
	return result
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
	if known == nil && w.order != nil {
		known = w.order[jsonpointer.FromTokens(path)]
	}
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
	path                             string
	cause                            error
	causes                           []error
	discriminator, discriminatorPath string
}

func (e *modelError) Error() string { return "sdl model rejected" }
func (e *modelError) Unwrap() error { return e.cause }

func (e *modelError) SourceDiagnostics() []source.Diagnostic {
	result := []source.Diagnostic{}
	for _, err := range e.causes {
		result = append(result, source.Diagnostics(err)...)
		if len(result) >= 20 {
			return result[:20]
		}
	}
	if len(result) == 0 {
		result = append(result, source.Diagnostic{Code: "sdl.model.invalid", Pointer: e.path, Severity: termError})
	}
	if e.discriminator != "" {
		for i := range result {
			prefix := e.discriminatorPath
			if result[i].Pointer == prefix || strings.HasPrefix(result[i].Pointer, prefix+"/") {
				result[i].Pointer = prefix + "/" + jsonpointer.EscapeToken(e.discriminator) + strings.TrimPrefix(result[i].Pointer, prefix)
			}
		}
	}
	return result
}

func modelDiscriminator(schema map[string]any, value any) string {
	selector := object(schema["discriminator"])
	property := text(selector["propertyName"])
	if tag, ok := object(value)[property].(string); ok && object(selector["mapping"])[tag] != nil {
		return tag
	}
	for _, raw := range alternatives(schema) {
		if tag := modelDiscriminator(object(raw), value); tag != "" {
			return tag
		}
	}
	return ""
}

package authoring

import (
	"bytes"
	"encoding/json"
	"errors"
	"maps"
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
}
type ordered []field

type normalizer struct {
	parser    *Parser
	id        string
	ranges    map[string]source.Range
	remaining int
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
func (w *normalizer) walk(schema map[string]any, pointer string, value any, path string) (result any, failure error) {
	defer func() {
		if failure != nil {
			if _, ok := errors.AsType[*modelError](failure); !ok {
				failure = &modelError{path: path, cause: failure}
			}
		}
	}()
	w.remaining--
	if w.remaining < 0 || strings.Count(path, "/") > w.parser.limits.MaxDepth {
		return nil, invalid()
	}
	schema, pointer = w.dereference(schema, pointer)
	if schema == nil {
		schema = map[string]any{}
	}
	if strings.HasSuffix(pointer, "/$defs/Source") {
		if s, ok := value.(string); ok {
			value = map[string]any{"name": s, "version": "*"}
		}
	}
	var err error
	value, err = w.scalar(schema, value)
	if err != nil {
		return nil, err
	}
	if branches := alternatives(schema); len(branches) > 0 {
		chosen, selected := w.choose(branches, value)
		if chosen != nil {
			return w.walk(chosen, selected, value, path)
		}
	}
	switch v := value.(type) {
	case map[string]any:
		return w.mapping(schema, pointer, v, path)
	case []any:
		result := make([]any, len(v))
		for i, item := range v {
			child := object(schema["items"])
			if positional := array(schema["prefixItems"]); i < len(positional) {
				child = object(positional[i])
			}
			result[i], err = w.walk(child, pointer+"/items", item, path+"/"+strconv.Itoa(i))
			if err != nil {
				return nil, err
			}
		}
		return result, nil
	default:
		return value, nil
	}
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
		if schemaMatches(schema, value) {
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
func (w *normalizer) mapping(schema map[string]any, pointer string, value map[string]any, path string) (any, error) {
	if err := w.modelInput(pointer, value); err != nil {
		return nil, err
	}
	props := object(schema["properties"])
	keys := w.keys(value, path)
	presentation := w.parser.layouts[w.id][pointer]
	if len(presentation.Fields) > 0 {
		keys = fieldOrder(keys, presentation.Fields)
	}
	result := make(ordered, 0, len(value))
	for _, name := range keys {
		child, known := props[name]
		if !known {
			child = schema["additionalProperties"]
		}
		raw, err := w.fieldInput(pointer, name, value[name])
		if err != nil {
			return nil, err
		}
		normalized, err := w.walk(object(child), pointer+"/properties/"+name, raw, path+"/"+jsonpointer.EscapeToken(name))
		if err != nil {
			return nil, err
		}
		if !omitted(normalized, presentation.Omit[name]) {
			result = append(result, field{name, normalized})
		}
	}
	return result, nil
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
	for _, policy := range policies {
		switch policy {
		case "always":
			return true
		case "null":
			if value == nil {
				return true
			}
		case "empty":
			if v, ok := value.(ordered); ok && len(v) == 0 {
				return true
			}
		case "blank":
			if value == "" {
				return true
			}
		case "false":
			if value == false {
				return true
			}
		}
	}
	return false
}
func writeJSON(out *bytes.Buffer, value any, limit int64) error {
	var raw []byte
	switch v := value.(type) {
	case float64:
		normalized, err := normalizeFloat(v)
		if err != nil {
			return err
		}
		raw = []byte(normalized.(json.Number))
	case ordered:
		if err := appendJSON(out, []byte{'{'}, limit); err != nil {
			return err
		}
		for i, entry := range v {
			if i > 0 {
				if err := appendJSON(out, []byte{','}, limit); err != nil {
					return err
				}
			}
			name, _ := json.Marshal(entry.name)
			if err := appendJSON(out, append(name, ':'), limit); err != nil {
				return err
			}
			if err := writeJSON(out, entry.value, limit); err != nil {
				return err
			}
		}
		raw = []byte{'}'}
	case []any:
		if err := appendJSON(out, []byte{'['}, limit); err != nil {
			return err
		}
		for i, item := range v {
			if i > 0 {
				if err := appendJSON(out, []byte{','}, limit); err != nil {
					return err
				}
			}
			if err := writeJSON(out, item, limit); err != nil {
				return err
			}
		}
		raw = []byte{']'}
	default:
		var err error
		raw, err = json.Marshal(value)
		if err != nil {
			return invalid()
		}
	}
	return appendJSON(out, raw, limit)
}
func appendJSON(out *bytes.Buffer, raw []byte, limit int64) error {
	if int64(len(raw)) > limit-int64(out.Len()) {
		return invalid()
	}
	_, _ = out.Write(raw)
	return nil
}

type modelError struct {
	path  string
	cause error
}

func (e *modelError) Error() string { return "sdl model rejected" }
func (e *modelError) Unwrap() error { return e.cause }

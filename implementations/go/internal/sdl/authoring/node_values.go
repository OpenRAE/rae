package authoring

import (
	"bytes"
	"encoding/json"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

const nodeSubject = "subject"

// NormalizeNodeValue applies the whole native node constructor and projects
// realizable children from its schema and typed defaults, without references.
func (p *Parser) NormalizeNodeValue(data []byte) ([]byte, map[string][]string, error) {
	if p == nil || p.models == nil {
		return nil, nil, invalid()
	}
	options := p.options("node-value", "reject")
	options.KeyScope = dataScope
	parsed, err := source.Decode(data, options)
	if err != nil {
		return nil, nil, err
	}
	wrapper := map[string]any{nameField: "node-value", nodesSection: map[string]any{nodeSubject: parsed.Value()}}
	queries := newScopeQueries(p, authoringContract, wrapper)
	rootSchema := object(object(p.schemas[authoringContract]["properties"])[nodesSection])
	nodeSchema := object(rootSchema["additionalProperties"])
	normalized, err := p.normalizeConcernField(queries, rootSchema, "#/properties/nodes", nodeSubject, parsed.Value(), nodeSchema, "#/properties/nodes/additionalProperties")
	if err != nil {
		return nil, nil, err
	}
	node, err := ingress.Parse(normalized, modelLimits(normalized), ingress.Object)
	if err != nil {
		return nil, nil, err
	}
	if valueErr := value.Validate(node, value.Runtime()); valueErr != nil {
		return nil, nil, valueErr
	}
	walk := typedPresenceWalk{queries: queries, presence: map[string][]string{}, defaults: map[string]nodeDefault{}, remaining: value.Runtime().MaxNodes}
	if presenceErr := walk.visit(node, nodeSchema, "#/properties/nodes/additionalProperties", "", 0); presenceErr != nil {
		return nil, nil, presenceErr
	}
	encoded, err := json.Marshal(node)
	return encoded, walk.presence, err
}

type nodeDefault struct {
	value   any
	present bool
}
type typedPresenceWalk struct {
	queries    *scopeQueries
	presence   map[string][]string
	defaults   map[string]nodeDefault
	remaining  int
	modelNames bool
}

func (w *typedPresenceWalk) visit(input any, schema map[string]any, pointer, path string, depth int) error {
	w.remaining--
	if w.remaining < 0 || depth > value.Runtime().MaxDepth {
		return value.ErrLimit
	}
	schema, pointer = w.queries.schema(schema, pointer, input)
	switch data := input.(type) {
	case map[string]any:
		return w.mapping(data, schema, pointer, path, depth)
	case []any:
		for i, child := range data {
			if err := w.visit(child, object(schema["items"]), pointer+"/items", path+"["+strconv.Itoa(i)+"]", depth+1); err != nil {
				return err
			}
		}
	}
	return nil
}
func nodeChildPath(path, field string) string {
	if path == "" {
		return field
	}
	return path + "." + field
}
func (w *typedPresenceWalk) mapping(data, schema map[string]any, pointer, path string, depth int) error {
	presentation, typed := w.queries.w.parser.lookupLayout(w.queries.w.id, pointer)
	if typed {
		children, err := w.children(data, schema, pointer)
		if err != nil {
			return err
		}
		w.presence[path] = children
	}
	for _, field := range orderedKeys(data, nil) {
		child, err := w.queries.w.propertySchema(schema, field)
		if err != nil {
			return err
		}
		name := field
		if w.modelNames {
			name = modelFieldName(presentation, field)
		}
		if err := w.visit(data[field], child, schemaPropertyPointer(schema, pointer, field), nodeChildPath(path, name), depth+1); err != nil {
			return err
		}
	}
	return nil
}
func nodeValueNonempty(input any) bool {
	switch data := input.(type) {
	case nil:
		return false
	case map[string]any:
		return len(data) > 0
	case []any:
		return len(data) > 0
	default:
		return true
	}
}
func (w *typedPresenceWalk) children(data, schema map[string]any, pointer string) ([]string, error) {
	children := []string{}
	required := map[string]bool{}
	for _, name := range array(schema["required"]) {
		required[text(name)] = true
	}
	for _, field := range orderedKeys(data, nil) {
		child, err := w.queries.w.propertySchema(schema, field)
		if err != nil {
			return nil, err
		}
		if child["x-raes-realization-dimension"] == false || !nodeValueNonempty(data[field]) {
			continue
		}
		name := w.presenceFieldName(pointer, field)
		if required[field] {
			children = append(children, name)
			continue
		}
		fallback, err := w.fieldDefault(schema, child, pointer, field)
		if err != nil {
			return nil, err
		}
		if !fallback.present || !nativeDefaultEqual(data[field], fallback.value) {
			children = append(children, name)
		}
	}
	slices.Sort(children)
	return children, nil
}
func (w *typedPresenceWalk) fieldDefault(schema, child map[string]any, pointer, field string) (nodeDefault, error) {
	key := pointer + "/" + field
	if stored, found := w.defaults[key]; found {
		return stored, nil
	}
	fallback, present, err := w.queries.defaultValue(pointer, field, child)
	if err != nil {
		return nodeDefault{}, err
	}
	result := nodeDefault{present: present}
	if present {
		raw, err := w.queries.w.parser.normalizeConcernField(w.queries, schema, pointer, field, fallback, child, schemaPropertyPointer(schema, pointer, field))
		if err != nil {
			return nodeDefault{}, err
		}
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.UseNumber()
		if err := decoder.Decode(&result.value); err != nil {
			return nodeDefault{}, err
		}
	}
	w.defaults[key] = result
	return result, nil
}

// Both operands were constructed by the same native field owner and contain
// exact JSON types only. The encoded forms retain constructor number types.
func nativeDefaultEqual(left, right any) bool {
	first, err := json.Marshal(left)
	if err != nil {
		return false
	}
	second, err := json.Marshal(right)
	return err == nil && bytes.Equal(first, second)
}

func (w *typedPresenceWalk) presenceFieldName(pointer, field string) string {
	if !w.modelNames {
		return field
	}
	return modelFieldName(w.queries.w.parser.layoutFor(w.queries.w.id, pointer), field)
}

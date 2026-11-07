package authoring

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

// Queries own their copied containers. Defaults never alter semantic input or
// formatter output, and unqueried subtrees retain their original storage.
type scopeQueries struct {
	w      normalizer
	value  any
	copied map[string]bool
}

func newScopeQueries(p *Parser, id string, value map[string]any) *scopeQueries {
	return &scopeQueries{w: normalizer{parser: p, id: id}, value: value, copied: map[string]bool{}}
}

func (q *scopeQueries) resolve(pointer string) (string, error) {
	tokens := jsonpointer.Tokens(pointer)
	if len(pointer) > 4096 || len(tokens) > 32 || jsonpointer.FromTokens(tokens) != pointer {
		return "", semanticInvalid()
	}
	current, schema := q.value, q.w.parser.schemas[q.w.id]
	sourcePath, schemaPointer := "", "#"
	assign := func(value any) { q.value = value }
	for index, token := range tokens {
		current = q.privateContainer(current, sourcePath, assign)
		schema, schemaPointer = q.schema(schema, schemaPointer, current)
		prefix := jsonpointer.FromTokens(tokens[:index+1])
		var err error
		current, schema, schemaPointer, assign, err = q.step(current, schema, schemaPointer, token, prefix)
		if err != nil {
			return "", err
		}
		sourcePath, _, err = admission.ResolveSDLObservationScope(q.value, prefix)
		if err != nil {
			return "", err
		}
	}
	_, canonical, err := admission.ResolveSDLObservationScope(q.value, pointer)
	return canonical, err
}

func (q *scopeQueries) privateContainer(value any, path string, assign func(any)) any {
	if q.copied[path] {
		return value
	}
	switch v := value.(type) {
	case map[string]any:
		value = maps.Clone(v)
	case []any:
		value = slices.Clone(v)
	default:
		return value
	}
	q.copied[path] = true
	assign(value)
	return value
}

func (q *scopeQueries) schema(schema map[string]any, pointer string, value any) (map[string]any, string) {
	for range 16 {
		schema, pointer = q.w.dereference(schema, pointer)
		if schema["properties"] != nil {
			return schema, pointer
		}
		chosen, selected := q.w.choose(alternatives(schema), value)
		if chosen == nil {
			return schema, pointer
		}
		schema, pointer = chosen, selected
	}
	return nil, ""
}

func (q *scopeQueries) step(current any, schema map[string]any, pointer, token, prefix string) (any, map[string]any, string, func(any), error) {
	switch value := current.(type) {
	case map[string]any:
		child, err := q.w.propertySchema(schema, token)
		if err != nil {
			return nil, nil, "", nil, err
		}
		if _, present := value[token]; !present {
			fallback, found, err := q.defaultValue(pointer, token, child)
			if err != nil || !found {
				return nil, nil, "", nil, semanticInvalid()
			}
			value[token] = fallback
		}
		return value[token], child, pointer + "/properties/" + jsonpointer.EscapeToken(token), func(next any) { value[token] = next }, nil
	case []any:
		source, _, err := admission.ResolveSDLObservationScope(q.value, prefix)
		if err != nil {
			return nil, nil, "", nil, err
		}
		tokens := jsonpointer.Tokens(source)
		index, ok := jsonpointer.ArrayIndex(tokens[len(tokens)-1], len(value))
		if !ok {
			return nil, nil, "", nil, semanticInvalid()
		}
		return value[index], object(schema["items"]), pointer + "/items", func(next any) { value[index] = next }, nil
	default:
		return nil, nil, "", nil, semanticInvalid()
	}
}

func (q *scopeQueries) defaultValue(pointer, field string, schema map[string]any) (any, bool, error) {
	raw, found := q.w.parser.layoutFor(q.w.id, pointer).FactoryDefaults[field]
	if !found {
		schema, _ = q.w.dereference(schema, "")
		value, present := schema[defaultField]
		if !present {
			return nil, false, nil
		}
		var err error
		raw, err = json.Marshal(value)
		if err != nil {
			return nil, false, err
		}
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var value any
	err := decoder.Decode(&value)
	return value, true, err
}

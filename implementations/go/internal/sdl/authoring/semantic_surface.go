package authoring

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type semanticSurface struct{ definition, nodeKind string }

// A realization designation addresses typed fields, including defaulted and
// null fields. Its arrays use numeric positions rather than observation IDs.
func (q *scopeQueries) surface(pointer string) (semanticSurface, error) {
	tokens := jsonpointer.Tokens(pointer)
	if len(pointer) > 4096 || jsonpointer.FromTokens(tokens) != pointer {
		return semanticSurface{}, semanticInvalid()
	}
	current, schema := q.value, q.w.parser.schemas[q.w.id]
	sourcePath, schemaPointer := "", "#"
	assign := func(value any) { q.value = value }
	for i, token := range tokens {
		current = q.privateContainer(current, sourcePath, assign)
		schema, schemaPointer = q.schema(schema, schemaPointer, current)
		prefix := jsonpointer.FromTokens(tokens[:i+1])
		var err error
		current, schema, schemaPointer, assign, err = q.surfaceStep(current, schema, schemaPointer, token, prefix)
		if err != nil {
			return semanticSurface{}, err
		}
		sourcePath = prefix
	}
	_, schemaPointer = q.schema(schema, schemaPointer, current)
	result := semanticSurface{definition: schemaPointer}
	if schemaPointer == "#/$defs/Node" {
		data, err := json.Marshal(current)
		if err != nil {
			return semanticSurface{}, err
		}
		var node struct {
			Kind string `json:"type"`
		}
		if json.Unmarshal(data, &node) != nil {
			return semanticSurface{}, invalid()
		}
		result.nodeKind = node.Kind
	}
	return result, nil
}
func (q *scopeQueries) surfaceStep(current any, schema map[string]any, pointer, token, prefix string) (any, map[string]any, string, func(any), error) {
	if values, ok := current.([]any); ok {
		index, valid := jsonpointer.ArrayIndex(token, len(values))
		if !valid {
			return nil, nil, "", nil, semanticInvalid()
		}
		return values[index], object(schema["items"]), pointer + "/items", func(next any) { values[index] = next }, nil
	}
	return q.step(current, schema, pointer, token, prefix)
}

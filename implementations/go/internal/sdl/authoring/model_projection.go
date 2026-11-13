package authoring

import "github.com/OpenRAE/rae/implementations/go/internal/base/value"

const (
	modelEditorialAll    = "all"
	modelEditorialNative = "native"
	modelEditorialField  = "description"
)

// modelProjection selects names and editorial fields only at their schema
// owner. It never interprets arbitrary payload member names as model metadata.
type modelProjection struct {
	queries    *scopeQueries
	editorial  string
	modelNames bool
	remaining  int
}

func modelFieldName(presentation layout, field string) string {
	if name, known := presentation.ModelNames[field]; known {
		return name
	}
	return field
}
func (w *modelProjection) project(input any, schema map[string]any, pointer string, depth int) (any, error) {
	w.remaining--
	if w.remaining < 0 || depth > value.Runtime().MaxDepth {
		return nil, value.ErrLimit
	}
	schema, pointer = w.queries.schema(schema, pointer, input)
	switch data := input.(type) {
	case map[string]any:
		return w.mapping(data, schema, pointer, depth)
	case []any:
		output := make([]any, len(data))
		for i, child := range data {
			projected, err := w.project(child, object(schema["items"]), pointer+"/items", depth+1)
			if err != nil {
				return nil, err
			}
			output[i] = projected
		}
		return output, nil
	default:
		return input, nil
	}
}
func (w *modelProjection) mapping(input, schema map[string]any, pointer string, depth int) (map[string]any, error) {
	owner := w.queries.w.parser.layoutFor(w.queries.w.id, pointer)
	output := make(map[string]any, len(input))
	for field, data := range input {
		if field == modelEditorialField && (w.editorial == modelEditorialAll || w.editorial == modelEditorialNative && owner.NativeSDL) {
			continue
		}
		child, err := w.queries.w.propertySchema(schema, field)
		if err != nil {
			return nil, err
		}
		projected, err := w.project(data, child, schemaPropertyPointer(schema, pointer, field), depth+1)
		if err != nil {
			return nil, err
		}
		name := field
		if w.modelNames {
			name = modelFieldName(owner, field)
		}
		output[name] = projected
	}
	return output, nil
}

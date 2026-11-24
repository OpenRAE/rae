package authoring

import (
	"bytes"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// A frame retains child schema context without defaulting the child's tree.
type semanticValueFrame struct {
	data           any
	schema         map[string]any
	pointer        string
	omitProvenance bool
}
type semanticValueProjection struct {
	queries *scopeQueries
	limits  value.Limits
}

func (p semanticValueProjection) project(input any) (any, error) {
	frame, ok := input.(semanticValueFrame)
	if !ok {
		return input, nil
	}
	frame.schema, frame.pointer = p.queries.schema(frame.schema, frame.pointer, frame.data)
	switch data := frame.data.(type) {
	case map[string]any:
		return p.mapping(frame, data)
	case []any:
		if len(data) > p.limits.MaxMembers {
			return nil, value.ErrLimit
		}
		result := make([]any, len(data))
		for i, child := range data {
			result[i] = semanticValueFrame{data: child, schema: object(frame.schema["items"]), pointer: frame.pointer + "/items"}
		}
		return result, nil
	case json.Number:
		// A constructed float field retains its float scalar cost even when
		// supplied as an integer token. JSON identity remains unchanged.
		if frame.schema["type"] == numberType {
			return data.Float64()
		}
	}
	return frame.data, nil
}
func (p semanticValueProjection) mapping(frame semanticValueFrame, data map[string]any) (any, error) {
	if len(data) > p.limits.MaxMembers {
		return nil, value.ErrLimit
	}
	result := make(map[string]any, len(data))
	for field, child := range data {
		if frame.omitProvenance && field == "materialization_provenance" {
			continue
		}
		schema, err := p.queries.w.propertySchema(frame.schema, field)
		if err != nil {
			return nil, err
		}
		result[field] = semanticValueFrame{data: child, schema: schema, pointer: frame.pointer + "/properties/" + jsonpointer.EscapeToken(field)}
	}
	return p.defaults(frame, data, result)
}
func (p semanticValueProjection) defaults(frame semanticValueFrame, data, result map[string]any) (any, error) {
	for field, raw := range object(frame.schema["properties"]) {
		if _, present := data[field]; present || frame.omitProvenance && field == "materialization_provenance" {
			continue
		}
		schema := object(raw)
		fallback, found, err := p.queries.defaultValue(frame.pointer, field, schema)
		if err != nil {
			return nil, err
		}
		if found {
			result[field] = semanticValueFrame{data: fallback, schema: schema, pointer: frame.pointer + "/properties/" + jsonpointer.EscapeToken(field)}
		}
	}
	return result, nil
}

func (m *semanticModel) portableMaterialized() error {
	if m.document.contract != materializedContract {
		return nil
	}
	projection := semanticValueProjection{queries: m.scopes, limits: value.Runtime()}
	root := semanticValueFrame{data: m.scopes.value, schema: m.parser.schemas[m.document.contract], pointer: "#", omitProvenance: true}
	return value.ValidateProjected(root, projection.limits, projection.project)
}
func (m *semanticModel) portableDescriptor(row semanticDescriptor) bool {
	projection := semanticValueProjection{queries: m.scopes, limits: value.Default()}
	var input map[string]any
	decoder := json.NewDecoder(bytes.NewReader(row.raw))
	decoder.UseNumber()
	if decoder.Decode(&input) != nil {
		return false
	}
	pointer := "#/$defs/DomainProfileBindingModel"
	schema := resolve(m.parser.schemas[m.document.contract], pointer)
	root := []any{semanticValueFrame{data: input, schema: schema, pointer: pointer}}
	return value.ValidateProjected(root, projection.limits, projection.project) == nil
}

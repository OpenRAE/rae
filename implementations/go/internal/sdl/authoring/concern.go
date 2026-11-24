package authoring

import (
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// NormalizeConcern applies the native field constructor without admitting a
// scenario or resolving references. The wrapper supplies only parent shapes.
func (p *Parser) NormalizeConcern(section string, path []string, data []byte) ([]byte, error) {
	if !p.concernPathSupported(section, path) {
		return nil, invalid()
	}
	options := p.options("realization-value", "reject")
	options.KeyScope = dataScope
	options.RequireMapping = false
	parsed, err := source.Decode(data, options)
	if err != nil {
		return nil, err
	}
	fieldValue := parsed.Value()
	for _, p := range slices.Backward(path) {
		fieldValue = map[string]any{p: fieldValue}
	}
	record := object(fieldValue)
	defaultConcernType(record, section)
	wrapper := map[string]any{nameField: "realization-value", section: map[string]any{nodeSubject: record}}
	queries := newScopeQueries(p, authoringContract, wrapper)
	schema, pointer, current := p.schemas[authoringContract], "#", any(wrapper)
	tokens := append([]string{section, nodeSubject}, path...)
	for index, token := range tokens {
		schema, pointer = queries.schema(schema, pointer, current)
		if schema == nil {
			return nil, invalid()
		}
		child, err := queries.w.propertySchema(schema, token)
		if err != nil {
			return nil, err
		}
		childPointer := pointer + "/additionalProperties"
		if _, known := object(schema["properties"])[token]; known {
			childPointer = pointer + "/properties/" + jsonpointer.EscapeToken(token)
		}
		next, present := object(current)[token]
		if !present {
			return nil, invalid()
		}
		if index != len(tokens)-1 {
			schema, pointer, current = child, childPointer, next
			continue
		}
		return p.normalizeConcernField(queries, schema, pointer, token, next, child, childPointer)
	}
	return nil, invalid()
}

func defaultConcernType(record map[string]any, section string) {
	if _, present := record["type"]; !present && section != infrastructureField {
		record["type"] = "compute"
		if section == contentField {
			record["type"] = "dataset"
		}
	}
}

func (p *Parser) concernPathSupported(section string, path []string) bool {
	if p == nil || p.models == nil || section != nodesSection && section != contentField && (section != infrastructureField || len(path) != 1 || path[0] != "count") || len(path) == 0 || len(path) > 16 {
		return false
	}
	for _, token := range path {
		if len(token) == 0 || len(token) > 64 || strings.IndexFunc(token, func(r rune) bool { return r != '_' && (r < 'a' || r > 'z') && (r < '0' || r > '9') }) >= 0 {
			return false
		}
	}
	return true
}
func (p *Parser) normalizeConcernField(queries *scopeQueries, schema map[string]any, pointer, token string, input any, child map[string]any, childPointer string) ([]byte, error) {
	fill := importDefaultWalk{queries: queries, remaining: compositionJSONWork(p.limits)}
	full, err := fill.value(input, child, childPointer)
	if err != nil {
		return nil, err
	}
	limit := jsonWorkingLimit(p.limits.MaxInputBytes, p.limits.MaxExpandedNodes)
	walk := normalizer{parser: p, id: queries.w.id, workingLimit: limit}
	field, err := walk.mappingField(schema, pointer, token, full, nil, mappingPresentation{layout: p.layoutFor(queries.w.id, pointer)}, source.View{})
	if err != nil {
		return nil, err
	}
	encoded, err := encode(field.value, limit, false)
	if err != nil {
		return nil, err
	}
	if err := p.models.CheckSDLConstruction(queries.w.id, childPointer, encoded, modelLimits(encoded)); err != nil {
		return nil, err
	}
	return encode(field.value, limit, true)
}

// AdmitInstantiatedSource retains native source order through concrete admission.
func (p *Parser) AdmitInstantiatedSource(data []byte, policy string) (*Document, error) {
	if p == nil || p.models == nil || policy != termAccept && policy != "reject" {
		return nil, invalid()
	}
	parsed, err := source.Decode(data, p.options("instantiated", policy))
	if err != nil {
		return nil, err
	}
	encoded, err := encode(sourceOrdered(parsed.NormalizedValue(), parsed.View()), compositionJSONWork(p.limits), false)
	if err != nil {
		return nil, err
	}
	return p.AdmitInstantiated(encoded)
}

func sourceOrdered(value any, view source.View) any {
	switch input := value.(type) {
	case map[string]any:
		result := make(ordered, 0, len(input))
		for _, name := range orderedKeys(input, view.Keys()) {
			result = append(result, field{name: name, value: sourceOrdered(input[name], view.Child(name))})
		}
		return result
	case []any:
		result := make([]any, len(input))
		for i, item := range input {
			result[i] = sourceOrdered(item, view.Child(strconv.Itoa(i)))
		}
		return result
	default:
		return value
	}
}

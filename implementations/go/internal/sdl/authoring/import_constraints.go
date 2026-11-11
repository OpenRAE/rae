package authoring

import (
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type importConstraintWalk struct {
	queries   *scopeQueries
	variables map[string]any
	preserved map[string]bool
	facts     *importFacts
	seen      map[string]bool
}

func (c *composition) captureImportConstraints(value map[string]any, preserved map[string]bool, facts *importFacts) error {
	walk := importConstraintWalk{queries: newScopeQueries(c.parser, authoringContract, value), variables: object(value[variablesSection]), preserved: preserved, facts: facts, seen: map[string]bool{}}
	for _, name := range orderedKeys(object(value[nodesSection]), facts.order["/nodes"]) {
		node := object(object(value[nodesSection])[name])
		path := []string{nodesSection, name}
		for _, field := range []string{"os", "os_distribution", "os_version", "architecture"} {
			walk.scalar(node[field], appendPath(path, field), false)
		}
		if err := walk.value(node[runtimeField], object(object(resolve(c.parser.schemas[authoringContract], "#/$defs/Node")["properties"])[runtimeField]), "#/$defs/Node/properties/runtime", appendPath(path, runtimeField)); err != nil {
			return err
		}
	}
	for _, name := range orderedKeys(object(value[infrastructureField]), facts.order["/infrastructure"]) {
		walk.scalar(object(object(value[infrastructureField])[name])[countField], []string{infrastructureField, name, countField}, false)
	}
	return nil
}

func (w *importConstraintWalk) scalar(value any, path []string, runtime bool) {
	text, isString := value.(string)
	if !isString {
		return
	}
	names := semanticVariableNames(text)
	if runtime && len(names) > 0 {
		w.derivation(text, path, names)
	}
	if !variable(text) {
		return
	}
	name := text[2 : len(text)-1]
	allowed := array(object(w.variables[name])[allowedValuesField])
	pointer := jsonpointer.FromTokens(path)
	if len(allowed) == 0 || w.preserved[name] || w.seen[pointer] {
		return
	}
	w.seen[pointer] = true
	w.facts.constraints = append(w.facts.constraints, importConstraint{Kind: "allowed-values", Pointer: pointer, Parameter: []string{name}, Allowed: slices.Clone(allowed)})
}

func (w *importConstraintWalk) derivation(text string, path, names []string) {
	for _, name := range names {
		if w.variables[name] == nil || w.preserved[name] {
			return
		}
	}
	if variable(text) && len(array(object(w.variables[text[2:len(text)-1]])[allowedValuesField])) > 0 {
		return
	}
	segments := []any{}
	offset := 0
	for _, match := range variableTokens.FindAllStringSubmatchIndex(text, -1) {
		if match[0] > offset {
			segments = append(segments, map[string]any{kindField: termLiteral, valueField: text[offset:match[0]]})
		}
		name := text[match[2]:match[3]]
		definition := object(w.variables[name])
		segments = append(segments, map[string]any{kindField: variationParameterKind, variationParameterKind: []any{name}, "variable_type": definition["type"], allowedValuesField: append([]any{}, array(definition[allowedValuesField])...)})
		offset = match[1]
	}
	if offset < len(text) {
		segments = append(segments, map[string]any{kindField: termLiteral, valueField: text[offset:]})
	}
	w.facts.derivations = append(w.facts.derivations, map[string]any{fieldPointerField: jsonpointer.FromTokens(path), "segments": segments})
}

func (w *importConstraintWalk) value(value any, schema map[string]any, pointer string, path []string) error {
	schema, pointer = w.queries.schema(schema, pointer, value)
	switch data := value.(type) {
	case map[string]any:
		return w.mapping(data, schema, pointer, path)
	case []any:
		for i, child := range data {
			if err := w.value(child, object(schema["items"]), pointer+"/items", appendPath(path, strconv.Itoa(i))); err != nil {
				return err
			}
		}
	default:
		w.scalar(data, path, true)
	}
	return nil
}

func (w *importConstraintWalk) mapping(data, schema map[string]any, pointer string, path []string) error {
	presentation, model := w.queries.w.parser.lookupLayout(authoringContract, pointer)
	keys := orderedKeys(data, w.facts.order[jsonpointer.FromTokens(path)])
	if model {
		keys = intentSuppliedFields(presentation, data)
	}
	classified := model && (presentation.CapabilityClassified || data["command_redacted"] == true)
	for _, field := range keys {
		child, err := w.queries.w.propertySchema(schema, field)
		if err != nil {
			return err
		}
		if classified && !slices.Contains(presentation.CapabilityPublic, field) || child["x-raes-realization-dimension"] == false {
			continue
		}
		if err := w.value(data[field], child, pointer+"/properties/"+jsonpointer.EscapeToken(field), appendPath(path, field)); err != nil {
			return err
		}
	}
	return nil
}

// Preserve stable map order for facts; missing generated keys use lexical order.
func orderedKeys(data map[string]any, known []string) []string {
	return (&normalizer{order: map[string][]string{"": known}}).keys(data, nil, source.View{})
}

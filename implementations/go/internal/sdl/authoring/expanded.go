package authoring

import (
	"encoding/json"
	"io/fs"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

const expandedContract = "sdl-expanded-authoring-object-v1"

func (p *Parser) loadSchemaViews(packaged fs.FS) error {
	for _, id := range []string{authoringContract, materializedContract, instantiatedContract} {
		raw, err := fs.ReadFile(packaged, "schemas/sdl/"+id+".json")
		if err != nil {
			return err
		}
		var schema map[string]any
		if err = json.Unmarshal(raw, &schema); err != nil {
			return err
		}
		p.schemas[id] = schema
		if err = p.checkLayout(id); err != nil {
			return err
		}
	}
	return p.loadExpandedSchema(packaged)
}

// This private view supports generated identities and provenance queries.
// Declaration fragments retain their published construction owner.
func (p *Parser) loadExpandedSchema(packaged fs.FS) error {
	raw, err := fs.ReadFile(packaged, "schemas/sdl/instantiated-scenario-v1.json")
	if err != nil {
		return err
	}
	var instantiated map[string]any
	if err = json.Unmarshal(raw, &instantiated); err != nil {
		return err
	}
	root := maps.Clone(p.schemas[authoringContract])
	definitions := maps.Clone(object(root["$defs"]))
	for name, schema := range object(instantiated["$defs"]) {
		if _, present := definitions[name]; !present {
			definitions[name] = schema
		}
	}
	phase := object(definitions["InstantiationProvenance"])
	phaseProperties := object(phase["properties"])
	expansion := map[string]any{}
	for _, name := range []string{importsField, termCapabilityConstraints, termParameterDerivations, termExplicitness, termRealizationDesignations, termRealizationConstraints} {
		expansion[name] = phaseProperties[name]
	}
	definitions["ExpansionProvenance"] = map[string]any{"type": termObject, "properties": expansion, "additionalProperties": false}
	root["$defs"] = definitions
	properties := maps.Clone(object(root["properties"]))
	for _, name := range []string{"module", importsField, "realization"} {
		delete(properties, name)
	}
	properties["expansion_provenance"] = map[string]any{"$ref": "#/$defs/ExpansionProvenance"}
	root["properties"] = properties
	p.schemas[expandedContract] = root
	return p.checkLayout(expandedContract)
}

type importOrigin struct {
	source, pointer string
	canonical       string
	position        source.Range
	located         bool
}

type importConstraint struct {
	Kind      string   `json:"kind"`
	Pointer   string   `json:"field_pointer"`
	Parameter []string `json:"parameter"`
	Allowed   []any    `json:"allowed_values"`
}

type importFacts struct {
	document     *Document
	explicitness []any
	order        map[string][]string
	constraints  []importConstraint
	bindings     []any
	designation  []any
	realization  []any
	derivations  []any
	origins      map[semanticOwner]importOrigin
}

func (c *composition) retainExpanded(document *Document, value map[string]any, name string) error {
	value = maps.Clone(value)
	delete(value, "module")
	delete(value, "realization")
	facts := c.facts[name]
	imports := make([]any, 0, len(c.records[name]))
	for _, record := range c.records[name] {
		imports = append(imports, record)
	}
	constraints := make([]any, 0, len(facts.constraints))
	for _, record := range facts.constraints {
		parameters := make([]any, len(record.Parameter))
		for i, parameter := range record.Parameter {
			parameters[i] = parameter
		}
		constraints = append(constraints, map[string]any{kindField: record.Kind, fieldPointerField: record.Pointer, variationParameterKind: parameters, allowedValuesField: record.Allowed})
	}
	provenance := map[string]any{
		importsField: imports, termCapabilityConstraints: constraints,
		termExplicitness: facts.explicitness, termRealizationDesignations: facts.designation,
		termRealizationConstraints: facts.realization,
	}
	if provenance[termExplicitness] == nil {
		provenance[termExplicitness] = []any{}
	}
	if len(facts.derivations) > 0 {
		provenance[termParameterDerivations] = facts.derivations
	}
	if err := c.checkExpandedFacts(facts, constraints); err != nil {
		return err
	}
	value["expansion_provenance"] = provenance
	limit := jsonWorkingLimit(c.parser.limits.MaxComposedBytes, c.parser.limits.MaxComposedNodes)
	walk := normalizer{parser: c.parser, id: expandedContract, workingLimit: limit, order: facts.order}
	normalized, err := walk.walk(c.parser.schemas[expandedContract], "#", value, nil, scalarPolicy{}, source.View{})
	if err != nil {
		return err
	}
	model, err := encode(normalized, limit, false)
	if err != nil {
		return err
	}
	serialized, err := encode(normalized, limit, true)
	if err != nil {
		return err
	}
	if err = c.modelAllowance().reserve(int64(len(model) + len(serialized))); err != nil {
		return err
	}
	snapshot := *document
	snapshot.contract, snapshot.data, snapshot.modelData = expandedContract, serialized, model
	snapshot.importOrigins = maps.Clone(facts.origins)
	document.expanded = &snapshot
	return nil
}

func (c *composition) checkMetadataFragment(definition string, value any) error {
	allowance := c.modelAllowance()
	data, err := encode(value, allowance.remaining, false)
	if err != nil {
		return err
	}
	if err = allowance.reserve(int64(len(data))); err != nil {
		return err
	}
	return c.parser.models.CheckModelFragment("instantiated-scenario-v1", "#/$defs/"+definition, data, modelLimits(data))
}

// The reference binds a complete serializer view, including constructor defaults.
func (c *composition) bindingPayload(value map[string]any, order map[string][]string) (map[string]any, error) {
	id := authoringContract
	if value["expansion_provenance"] != nil {
		id = expandedContract
	}
	queries := newScopeQueries(c.parser, id, value)
	fill := importDefaultWalk{queries: queries, remaining: compositionJSONWork(c.parser.limits)}
	full, err := fill.value(value, c.parser.schemas[id], "#")
	if err != nil {
		return nil, err
	}
	walk := normalizer{parser: c.parser, id: id, workingLimit: compositionJSONWork(c.parser.limits), order: order}
	normalized, err := walk.walk(c.parser.schemas[id], "#", full, nil, scalarPolicy{}, source.View{})
	if err != nil {
		return nil, err
	}
	return object(modelValue(normalized)), nil
}

type importDefaultWalk struct {
	queries   *scopeQueries
	remaining int64
}

func (w *importDefaultWalk) value(value any, schema map[string]any, pointer string) (any, error) {
	w.remaining--
	if w.remaining < 0 {
		return nil, fault.New(fault.InvalidInput, "sdl.import.budget-exceeded", nil)
	}
	schema, pointer = w.queries.schema(schema, pointer, value)
	switch data := value.(type) {
	case map[string]any:
		return w.mapping(data, schema, pointer)
	case []any:
		if int64(len(data)) > w.remaining {
			return nil, importError("budget-exceeded")
		}
		result := slices.Clone(data)
		for i, child := range data {
			var err error
			result[i], err = w.value(child, object(schema["items"]), pointer+"/items")
			if err != nil {
				return nil, err
			}
		}
		return result, nil
	default:
		return value, nil
	}
}

func (w *importDefaultWalk) mapping(data, schema map[string]any, pointer string) (any, error) {
	if int64(len(data)) > w.remaining {
		return nil, importError("budget-exceeded")
	}
	result := maps.Clone(data)
	for field, raw := range object(schema["properties"]) {
		if _, present := result[field]; present || pointer == "#/$defs/RuntimeServiceListener" && field == "protocol" {
			continue
		}
		fallback, found, err := w.queries.defaultValue(pointer, field, object(raw))
		if err != nil {
			return nil, err
		}
		if found {
			result[field] = fallback
		}
	}
	for field, child := range result {
		definition, err := w.queries.w.propertySchema(schema, field)
		if err != nil {
			return nil, err
		}
		result[field], err = w.value(child, definition, pointer+"/properties/"+field)
		if err != nil {
			return nil, err
		}
	}
	return result, nil
}

func (c *composition) checkExpandedFacts(facts *importFacts, constraints []any) error {
	for _, group := range []struct {
		definition string
		values     []any
	}{
		{"CapabilityConstraint", constraints}, {"ParameterDerivation", facts.derivations}, {"ExplicitnessProvenanceRecord", facts.explicitness},
		{"RealizationDesignationRecord", facts.designation}, {"RealizationConstraintRecord", facts.realization},
	} {
		for _, record := range group.values {
			if err := c.checkMetadataFragment(group.definition, record); err != nil {
				return err
			}
		}
	}
	return nil
}

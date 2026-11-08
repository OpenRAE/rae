package authoring

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func newImportFacts(document *Document, value map[string]any) (*importFacts, error) {
	result := &importFacts{origins: map[semanticOwner]importOrigin{}, constraints: []importConstraint{}, bindings: []any{}, designation: []any{}, realization: []any{}}
	var err error
	result.order, err = semanticOrder(document.modelBytes())
	if err != nil {
		return nil, err
	}
	collector := newSemanticCollector(document)
	for owner, position := range collector.locations {
		finding := collector.finding(owner, "", "error")
		result.origins[owner] = importOrigin{source: document.sourceName, pointer: finding.Pointer, canonical: finding.Pointer, position: position, located: true}
	}
	captureEntityOrigins(result.origins, document.source.View().Child(entitiesField), "", []string{entitiesField}, document.sourceName)
	if realization := object(value["realization"]); realization != nil {
		posture := realization[defaultField]
		if posture == nil {
			posture = "unspecified"
		}
		root := map[string]any{namespaceField: []any{}, fieldPointerField: "", "posture": posture}
		result.designation = append(result.designation, root)
		result.designation = append(result.designation, array(realization[scopesField])...)
		result.realization = append(result.realization, array(realization["constraints"])...)
	}
	return result, nil
}

func captureEntityOrigins(origins map[semanticOwner]importOrigin, view source.View, prefix string, tokens []string, sourceName string) {
	for _, member := range view.Members() {
		name, _ := member.Key.Scalar()
		path := appendPath(tokens, name)
		position, located := member.Key.Range()
		pointer := jsonpointer.FromTokens(path)
		origins[semanticOwner{entitiesField, prefix + name}] = importOrigin{source: sourceName, pointer: pointer, canonical: pointer, position: position, located: located}
		captureEntityOrigins(origins, member.Value.Child(entitiesField), prefix+name+".", appendPath(path, entitiesField), sourceName)
	}
}

func (c *composition) inheritImportFacts(parent, child, namespace string, symbols importSymbols) {
	into, from := c.facts[parent], c.facts[child]
	inheritImportOrder(into.order, from.order, symbols)
	for _, constraint := range from.constraints {
		constraint.Pointer = symbols.pointer(constraint.Pointer)
		constraint.Parameter = append([]string{namespace}, constraint.Parameter...)
		into.constraints = append(into.constraints, constraint)
	}
	into.derivations = append(into.derivations, qualifyDerivations(from.derivations, namespace, symbols)...)
	for owner, origin := range from.origins {
		owner = namespaceOriginOwner(owner, origin, symbols)
		origin.canonical = symbols.pointer(origin.canonical)
		into.origins[owner] = origin
	}
	into.designation = append(into.designation, qualifyRealization(from.designation, namespace, symbols)...)
	into.realization = append(into.realization, qualifyRealization(from.realization, namespace, symbols)...)
}

func qualifyDerivations(records []any, namespace string, symbols importSymbols) []any {
	result := make([]any, 0, len(records))
	for _, derivation := range records {
		row := maps.Clone(object(derivation))
		row[fieldPointerField] = symbols.pointer(text(row[fieldPointerField]))
		segments := make([]any, 0, len(array(row["segments"])))
		for _, segment := range array(row["segments"]) {
			part := maps.Clone(object(segment))
			if part[kindField] == variationParameterKind {
				part[variationParameterKind] = append([]any{namespace}, array(part[variationParameterKind])...)
			}
			segments = append(segments, part)
		}
		row["segments"] = segments
		result = append(result, row)
	}
	return result
}

func inheritImportOrder(into, from map[string][]string, symbols importSymbols) {
	for pointer, keys := range from {
		tokens := jsonpointer.Tokens(pointer)
		if len(tokens) == 1 && symbols[tokens[0]] != nil {
			for _, key := range keys {
				if renamed, present := symbols[tokens[0]][key]; present {
					into[pointer] = append(into[pointer], renamed)
				}
			}
		} else if len(tokens) >= 2 {
			into[symbols.pointer(pointer)] = slices.Clone(keys)
		}
	}
}

func namespaceOriginOwner(owner semanticOwner, origin importOrigin, symbols importSymbols) semanticOwner {
	if renamed, present := symbols[owner.section][owner.name]; present {
		return semanticOwner{owner.section, renamed}
	}
	tokens := jsonpointer.Tokens(origin.canonical)
	if len(tokens) >= 2 {
		if renamed, present := symbols[owner.section][tokens[1]]; present && strings.HasPrefix(owner.name, tokens[1]+".") {
			return semanticOwner{owner.section, renamed + owner.name[len(tokens[1]):]}
		}
	}
	return owner
}

func qualifyRealization(records []any, namespace string, symbols importSymbols) []any {
	result := make([]any, 0, len(records))
	for _, record := range records {
		row := maps.Clone(object(record))
		row[namespaceField] = append([]any{namespace}, array(row[namespaceField])...)
		row[fieldPointerField] = symbols.pointer(text(row[fieldPointerField]))
		result = append(result, row)
	}
	return result
}

func (d *Document) canonicalExpanded() ([]byte, error) {
	var scenario map[string]json.RawMessage
	if err := json.Unmarshal(d.expanded.data, &scenario); err != nil {
		return nil, fault.New(fault.Operational, "sdl-canonical-model", nil)
	}
	var provenance struct {
		Constraints []struct {
			Parameter []string        `json:"parameter"`
			Pointer   string          `json:"field_pointer"`
			Allowed   json.RawMessage `json:"allowed_values"`
		} `json:"capability_constraints"`
	}
	if err := json.Unmarshal(scenario["expansion_provenance"], &provenance); err != nil {
		return nil, fault.New(fault.Operational, "sdl-canonical-model", nil)
	}
	delete(scenario, "expansion_provenance")
	if string(scenario[variationPointsField]) == "{}" {
		delete(scenario, variationPointsField)
	}
	variables := map[string]map[string]json.RawMessage{}
	nodes := map[string]map[string]*string{}
	for _, constraint := range provenance.Constraints {
		parts := slices.Clone(constraint.Parameter)
		if len(parts) > 1 {
			parts = append(parts[:len(parts)-1], "__private", parts[len(parts)-1])
		}
		name := strings.Join(parts, ".")
		variables[name] = map[string]json.RawMessage{allowedValuesField: constraint.Allowed}
		tokens := jsonpointer.Tokens(constraint.Pointer)
		if len(tokens) == 3 && (tokens[0] == nodesSection && (tokens[2] == "os" || tokens[2] == "architecture") || tokens[0] == infrastructureField && tokens[2] == countField) {
			if nodes[tokens[1]] == nil {
				nodes[tokens[1]] = map[string]*string{"os": nil, countField: nil}
			}
			nodes[tokens[1]][tokens[2]] = &name
		}
	}
	return canonicalSemanticJSON(json.Marshal(map[string]any{"profile": semanticProfile, "scenario": scenario, "module_variable_specs": variables, "module_node_variable_refs": nodes}))
}

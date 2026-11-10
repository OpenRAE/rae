package authoring

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type concreteBinding struct {
	Parameter []string `json:"parameter"`
	Value     any      `json:"value"`
}
type concreteExplicitness struct {
	Path           string     `json:"model_path"`
	Classification string     `json:"classification"`
	Provenance     string     `json:"provenance"`
	Reason         string     `json:"reason"`
	Parameters     [][]string `json:"parameters"`
}
type concreteDerivation struct {
	Pointer  string `json:"field_pointer"`
	Segments []struct {
		Kind         string   `json:"kind"`
		Value        string   `json:"value"`
		Parameter    []string `json:"parameter"`
		VariableType string   `json:"variable_type"`
		Allowed      []any    `json:"allowed_values"`
	} `json:"segments"`
}
type concreteProvenance struct {
	Bindings []concreteBinding `json:"bindings"`
	Imports  []struct {
		Namespace []string          `json:"namespace"`
		Bindings  []concreteBinding `json:"bindings"`
	} `json:"imports"`
	Constraints  []importConstraint     `json:"capability_constraints"`
	Derivations  []concreteDerivation   `json:"parameter_derivations"`
	Explicitness []concreteExplicitness `json:"explicitness"`
	Designations []struct {
		Namespace []string `json:"namespace"`
		Pointer   string   `json:"field_pointer"`
	} `json:"realization_designations"`
	Realization []struct {
		Namespace []string `json:"namespace"`
		Pointer   string   `json:"field_pointer"`
		Concern   string   `json:"concern"`
	} `json:"realization_constraints"`
}

func (p *Parser) checkInstantiationProvenance(payload map[string]any) error {
	raw, err := json.Marshal(payload["instantiation_provenance"])
	if err != nil {
		return err
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var provenance concreteProvenance
	if decoder.Decode(&provenance) != nil {
		return invalid()
	}
	bindings, err := provenance.bindingEnvironment()
	if err != nil {
		return err
	}
	if err = provenance.checkIdentities(bindings); err != nil {
		return err
	}
	fields, err := p.concreteConstraintFields(payload, provenance.Constraints, bindings)
	if err != nil {
		return err
	}
	for _, record := range provenance.Derivations {
		if fields[record.Pointer] {
			return invalid()
		}
		fields[record.Pointer] = true
		value, err := record.resolve(bindings)
		if err != nil || !p.concreteOutputMatches(payload, record.Pointer, value) {
			return invalid()
		}
	}
	return nil
}

func (p *Parser) concreteConstraintFields(payload map[string]any, constraints []importConstraint, bindings map[string]any) (map[string]bool, error) {
	domains := map[string][]any{}
	fields := map[string]bool{}
	for _, record := range constraints {
		identity := parameterIdentity(record.Parameter)
		value, exists := bindings[identity]
		if !exists || fields[record.Pointer] || !concreteAllowed(value, record.Allowed) {
			return nil, invalid()
		}
		fields[record.Pointer] = true
		if prior, known := domains[identity]; known && !sameConcreteDomain(prior, record.Allowed) {
			return nil, invalid()
		}
		domains[identity] = record.Allowed
		if !p.concreteOutputMatches(payload, record.Pointer, value) {
			return nil, invalid()
		}
	}
	return fields, nil
}
func parameterIdentity(parts []string) string { return strings.Join(parts, "\x00") }
func (p concreteProvenance) bindingEnvironment() (map[string]any, error) {
	bindings := map[string]any{}
	add := func(prefix []string, rows []concreteBinding) error {
		for _, binding := range rows {
			if len(binding.Parameter) != 1 {
				return invalid()
			}
			identity := parameterIdentity(append(slices.Clone(prefix), binding.Parameter...))
			if _, exists := bindings[identity]; exists {
				return invalid()
			}
			bindings[identity] = binding.Value
		}
		return nil
	}
	if err := add(nil, p.Bindings); err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	for _, record := range p.Imports {
		identity := parameterIdentity(record.Namespace)
		if seen[identity] || len(record.Namespace) == 0 {
			return nil, invalid()
		}
		seen[identity] = true
		if err := add(record.Namespace, record.Bindings); err != nil {
			return nil, err
		}
	}
	return bindings, nil
}
func (p concreteProvenance) checkIdentities(bindings map[string]any) error {
	seen := map[string]bool{}
	for _, record := range p.Explicitness {
		if seen[record.Path] {
			return invalid()
		}
		seen[record.Path] = true
		for _, identity := range record.Parameters {
			if _, present := bindings[parameterIdentity(identity)]; !present {
				return invalid()
			}
		}
	}
	seen = map[string]bool{}
	for _, record := range p.Designations {
		identity := parameterIdentity(record.Namespace) + "\x01" + record.Pointer
		if seen[identity] {
			return invalid()
		}
		seen[identity] = true
	}
	seen = map[string]bool{}
	for _, record := range p.Realization {
		identity := parameterIdentity(record.Namespace) + "\x01" + record.Pointer + "\x01" + record.Concern
		if seen[identity] {
			return invalid()
		}
		seen[identity] = true
	}
	return nil
}
func concreteAllowed(value any, alternatives []any) bool {
	return slices.ContainsFunc(alternatives, func(member any) bool { return domain.Equal(value, member) })
}
func sameConcreteDomain(first, second []any) bool {
	if len(first) != len(second) {
		return false
	}
	for _, value := range first {
		if !concreteAllowed(value, second) {
			return false
		}
	}
	return true
}

func (d concreteDerivation) resolve(bindings map[string]any) (any, error) {
	values := []any{}
	declarations := map[string][]byte{}
	for _, segment := range d.Segments {
		if segment.Kind == termLiteral {
			values = append(values, segment.Value)
			continue
		}
		identity := parameterIdentity(segment.Parameter)
		value, present := bindings[identity]
		if !present || !variableType(value, segment.VariableType) || len(segment.Allowed) > 0 && !concreteAllowed(value, segment.Allowed) {
			return nil, invalid()
		}
		declaration, err := json.Marshal(segment)
		if err != nil {
			return nil, err
		}
		if prior, known := declarations[identity]; known && !bytes.Equal(prior, declaration) {
			return nil, invalid()
		}
		declarations[identity] = declaration
		values = append(values, value)
	}
	if len(declarations) == 0 {
		return nil, invalid()
	}
	return d.render(values), nil
}
func (d concreteDerivation) render(values []any) any {
	if len(d.Segments) == 1 && d.Segments[0].Kind == variationParameterKind {
		return values[0]
	}
	var rendered strings.Builder
	for _, value := range values {
		rendered.WriteString(pythonScalar(value))
	}
	return rendered.String()
}

// Compare using the same owning leaf constructor that produced the field.
func (p *Parser) concreteOutputMatches(root map[string]any, pointer string, value any) bool {
	concrete, present := provenancePointer(root, pointer)
	if !present {
		return false
	}
	if domain.Equal(concrete, value) {
		return true
	}
	tokens := jsonpointer.Tokens(pointer)
	if len(tokens) < 2 {
		return false
	}
	parentPointer := jsonpointer.FromTokens(tokens[:len(tokens)-1])
	parent, present := provenancePointer(root, parentPointer)
	owner := object(parent)
	if !present || owner == nil {
		return false
	}
	queries := newScopeQueries(p, instantiatedContract, root)
	surface, err := queries.surface(parentPointer)
	if err != nil || surface.definition == "#" {
		return false
	}
	if _, model := p.lookupLayout(instantiatedContract, surface.definition); !model {
		return false
	}
	candidate := maps.Clone(owner)
	candidate[tokens[len(tokens)-1]] = value
	walk := normalizer{parser: p, id: instantiatedContract, workingLimit: compositionJSONWork(p.limits)}
	normalized, err := walk.walk(resolve(p.schemas[instantiatedContract], surface.definition), surface.definition, candidate, nil, scalarPolicy{}, source.View{})
	if err != nil {
		return false
	}
	return domain.Equal(concrete, object(modelValue(normalized))[tokens[len(tokens)-1]])
}

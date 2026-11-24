package authoring

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func (m *semanticModel) parameterDerivationFacts() error {
	m.derivations = map[string]concreteDerivation{}
	rows := array(object(m.root["instantiation_provenance"])[termParameterDerivations])
	for _, row := range rows {
		raw, err := json.Marshal(row)
		if err != nil {
			return invalid()
		}
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.UseNumber()
		var record concreteDerivation
		if decoder.Decode(&record) != nil {
			return invalid()
		}
		if _, duplicate := m.derivations[record.Pointer]; duplicate {
			return invalid()
		}
		m.derivations[record.Pointer] = record
	}
	return nil
}

// ParameterDerivationImage computes one finite image with the native scalar
// renderer and owning leaf constructor. An unenumerated input returns nil;
// found distinguishes this from a leaf without parameter provenance.
func (d *Document) ParameterDerivationImage(fieldPointer string) (json.RawMessage, bool, error) {
	if d == nil || !d.Validated() || d.contract != instantiatedContract || len(fieldPointer) > 4096 || jsonpointer.FromTokens(jsonpointer.Tokens(fieldPointer)) != fieldPointer {
		return nil, false, invalid()
	}
	record, found := d.semantic.derivations[fieldPointer]
	if !found {
		return nil, false, nil
	}
	alternatives, finite, err := parameterImageAlternatives(record)
	if err != nil || !finite {
		return nil, true, err
	}
	limits := value.Default()
	if len(alternatives) > limits.MaxMembers {
		return nil, true, invalid()
	}
	result := []any{}
	seen := map[string]bool{}
	total := 0
	for _, alternative := range alternatives {
		rendered, key, memberErr := d.parameterImageMember(fieldPointer, record, alternative, limits)
		if memberErr != nil {
			return nil, true, memberErr
		}
		if !seen[key] {
			seen[key] = true
			total += len(pythonScalar(rendered))
			if total > limits.MaxTotalScalarBytes {
				return nil, true, invalid()
			}
			result = append(result, rendered)
		}
	}
	encoded, err := json.Marshal(result)
	return encoded, true, err
}

func parameterImageAlternatives(record concreteDerivation) ([]any, bool, error) {
	identities := map[string][]any{}
	for _, segment := range record.Segments {
		if segment.Kind != variationParameterKind {
			continue
		}
		if len(segment.Allowed) == 0 {
			return nil, false, nil
		}
		identities[parameterIdentity(segment.Parameter)] = segment.Allowed
	}
	if len(identities) != 1 {
		return nil, false, invalid()
	}
	for _, alternatives := range identities {
		return alternatives, true, nil
	}
	return nil, false, invalid()
}
func (d *Document) parameterImageMember(pointer string, record concreteDerivation, alternative any, limits value.Limits) (any, string, error) {
	if value.Validate(alternative, limits) != nil {
		return nil, "", invalid()
	}
	parts := make([]any, len(record.Segments))
	for i, segment := range record.Segments {
		parts[i] = alternative
		if segment.Kind == termLiteral {
			parts[i] = segment.Value
		}
	}
	rendered, err := d.semantic.parser.concreteOutputValue(d.semantic.root, pointer, record.render(parts))
	if err != nil || value.Validate(rendered, limits) != nil {
		return nil, "", invalid()
	}
	kind := "scalar"
	if number, ok := rendered.(json.Number); ok && strings.ContainsAny(number.String(), ".eE") {
		kind = termFloat
	}
	key, err := jsonIdentity(map[string]any{kindField: kind, "value": rendered})
	if err != nil {
		return nil, "", invalid()
	}
	return rendered, key, nil
}

// Keep the existing field constructor in one owner for provenance admission
// and finite-image lowering. This helper grants no new reference authority.
func (p *Parser) concreteOutputValue(root map[string]any, pointer string, input any) (any, error) {
	tokens := jsonpointer.Tokens(pointer)
	if len(tokens) < 2 {
		return nil, invalid()
	}
	owner, definition, path, err := p.provenanceConstructor(root, tokens)
	if err != nil {
		return nil, err
	}
	candidate, err := replaceProvenancePath(owner, path, input)
	if err != nil {
		return nil, err
	}
	walk := normalizer{parser: p, id: instantiatedContract, workingLimit: compositionJSONWork(p.limits)}
	normalized, err := walk.walk(resolve(p.schemas[instantiatedContract], definition), definition, candidate, nil, scalarPolicy{}, source.View{})
	if err != nil {
		return nil, err
	}
	output, present := provenancePointer(modelValue(normalized), jsonpointer.FromTokens(path))
	if !present {
		return nil, invalid()
	}
	return output, nil
}

func (p *Parser) provenanceConstructor(root map[string]any, tokens []string) (map[string]any, string, []string, error) {
	queries := newScopeQueries(p, instantiatedContract, root)
	for end := len(tokens) - 1; end >= 2; end-- {
		pointer := jsonpointer.FromTokens(tokens[:end])
		parent, present := provenancePointer(root, pointer)
		owner := object(parent)
		if !present || owner == nil {
			continue
		}
		surface, err := queries.surface(pointer)
		if err != nil {
			return nil, "", nil, err
		}
		if _, model := p.lookupLayout(instantiatedContract, surface.definition); model && surface.definition != "#" {
			return owner, surface.definition, tokens[end:], nil
		}
	}
	return nil, "", nil, invalid()
}

func replaceProvenancePath(current any, tokens []string, input any) (any, error) {
	if len(tokens) == 0 {
		return input, nil
	}
	switch value := current.(type) {
	case map[string]any:
		child, present := value[tokens[0]]
		if !present {
			return nil, invalid()
		}
		next, err := replaceProvenancePath(child, tokens[1:], input)
		if err != nil {
			return nil, err
		}
		result := maps.Clone(value)
		result[tokens[0]] = next
		return result, nil
	case []any:
		index, valid := jsonpointer.ArrayIndex(tokens[0], len(value))
		if !valid {
			return nil, invalid()
		}
		next, err := replaceProvenancePath(value[index], tokens[1:], input)
		if err != nil {
			return nil, err
		}
		result := slices.Clone(value)
		result[index] = next
		return result, nil
	default:
		return nil, invalid()
	}
}

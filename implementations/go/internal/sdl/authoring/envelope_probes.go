package authoring

import (
	"encoding/json"
	"maps"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// EnvelopeProbeCandidates supplies native model/enum facts to the shared relation.
// The returned candidates still require ordinary SDL and membership admission.
func (p *Parser) EnvelopeProbeCandidates(document *Document, envelope binding.RealizationEnvelopeV1, positive bool) ([]admission.EnvelopeProbeCandidate, []diagnostic.Diagnostic, error) {
	data, queries, err := p.envelopeConstructed(document)
	if err != nil {
		return nil, nil, err
	}
	scopes := map[string]admission.EnvelopeProbeScope{}
	walk := typedPresenceWalk{queries: queries, presence: map[string][]string{}, defaults: map[string]nodeDefault{}, remaining: value.Runtime().MaxNodes, modelNames: true, probes: scopes}
	if err = walk.visit(data, p.schemas[document.contract], "#", "", 0); err != nil {
		return nil, nil, err
	}
	selected := make([]admission.EnvelopeProbeScope, 0, len(scopes))
	for _, path := range slices.Sorted(maps.Keys(scopes)) {
		selected = append(selected, scopes[path])
	}
	return admission.EnvelopeProbeCandidates(p.models, envelope, selected, positive)
}
func (w *typedPresenceWalk) probeScope(data, schema map[string]any, pointer, path string, presentation layout) (admission.EnvelopeProbeScope, error) {
	result := admission.EnvelopeProbeScope{Path: path}
	for _, field := range slices.Sorted(maps.Keys(object(schema["properties"]))) {
		child, err := w.queries.w.propertySchema(schema, field)
		if err != nil {
			return result, err
		}
		current, present := data[field]
		if !present {
			fallback, err := w.fieldDefault(schema, child, pointer, field)
			if err != nil {
				return result, err
			}
			if !fallback.present {
				continue
			}
			current = fallback.value
		}
		policy := presentation.Scalar[field]
		enums := w.probeEnumMembers(child, policy, current)
		variants := extraProbeValues(current, enums)
		result.Fields = append(result.Fields, admission.EnvelopeProbeField{Name: modelFieldName(presentation, field), Variations: variants, EnumMembers: enums})
	}
	return result, nil
}
func (w *typedPresenceWalk) probeEnumMembers(schema map[string]any, policy scalarPolicy, current any) []any {
	text, ok := current.(string)
	if !ok {
		return nil
	}
	converted := slices.Contains(policy.Convert, "enum") || slices.Contains(policy.Convert, "vocabulary") || slices.Contains(policy.Convert, "account-vocabulary")
	resolved, _ := w.queries.schema(schema, "", current)
	if !converted && (schema["$ref"] == nil || resolved["enum"] == nil) {
		return nil
	}
	members := w.queries.w.enumMembers(schema, 0)
	if !slices.ContainsFunc(members, func(member any) bool { return member == text }) {
		return nil
	}
	return members
}
func extraProbeValues(current any, enums []any) []any {
	if len(enums) > 0 {
		result := []any{}
		for _, member := range enums {
			if member != current {
				result = append(result, member)
			}
		}
		return result
	}
	switch actual := current.(type) {
	case bool:
		return []any{!actual}
	case string:
		if actual == termOutOfEnvelope {
			return []any{"out-of-envelope-x"}
		}
		return []any{termOutOfEnvelope}
	case json.Number:
		return extraNumericProbe(actual)
	case float64:
		return []any{actual + 1}
	case map[string]any:
		return []any{map[string]any{termOutOfEnvelope: termOutOfEnvelope}}
	case []any:
		return []any{[]any{termOutOfEnvelope}}
	}
	return nil
}

func extraNumericProbe(actual json.Number) []any {
	if strings.ContainsAny(actual.String(), ".eE") {
		number, err := actual.Float64()
		if err == nil {
			return []any{number + 1}
		}
		return nil
	}
	number, ok := new(big.Int).SetString(actual.String(), 10)
	if ok {
		return []any{json.Number(number.Add(number, big.NewInt(1)).String())}
	}
	return nil
}

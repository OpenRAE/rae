package admission

import (
	"cmp"
	"encoding/json"
	"maps"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
)

// EnvelopeWitnessProjection assembles a deterministic bounded candidate through
// the existing envelope owner. The SDL owner must still admit and instantiate it.
//
//nolint:ireturn // The public contract returns the existing sealed fragment type.
func EnvelopeWitnessProjection(v *Validator, envelope binding.RealizationEnvelopeV1) (Fragment, []diagnostic.Diagnostic, error) {
	document, err := realizationOfferEnvelope(v, envelope)
	if err != nil {
		return nil, nil, err
	}
	expression := at(document, "expression")
	offer, err := materializationOfferFor(expression)
	if err != nil {
		return nil, nil, err
	}
	if findings := offer.invalidDiagnostics(); len(findings) > 0 {
		return nil, findings, nil
	}
	payload, findings := offer.witnessPayload(object(at(expression, "witness_policy", "selections")))
	if len(findings) > 0 {
		return nil, findings, nil
	}
	result, err := AdmitFragment(v, RealizationValue, payload, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
	return result, findings, err
}
func (o *materializationOffer) witnessPayload(selections map[string]any) (map[string]any, []diagnostic.Diagnostic) {
	payload := map[string]any{}
	findings := []diagnostic.Diagnostic{}
	for _, path := range slices.Sorted(maps.Keys(o.leaves)) {
		leaf := o.leaves[path]
		chosen, selected := selections[leaf.domainName]
		message := ""
		if !selected {
			chosen, message = defaultEnvelopeWitness(leaf.descriptor)
		}
		if message == "" {
			message = assignEnvelopePath(payload, path, chosen)
		}
		if message != "" {
			findings = append(findings, realizationOfferFinding("witness.no-witness", path, message))
		}
	}
	return payload, findings
}
func defaultEnvelopeWitness(descriptor any) (any, string) {
	switch stringAt(descriptor, termKind) {
	case postureExact:
		return at(descriptor, "value"), ""
	case termEnum:
		values := slices.Clone(array(at(descriptor, "values")))
		if len(values) == 0 {
			return nil, termRecordDomainsAreNotScalarWitnessLeaves
		}
		slices.SortStableFunc(values, compareEnvelopeScalars)
		return values[0], ""
	case typeBoolean:
		if at(descriptor, "value") != nil {
			return at(descriptor, "value"), ""
		}
		return false, ""
	case termGovernedReference:
		values := stringsOf(at(descriptor, "allowed_refs"))
		slices.Sort(values)
		if len(values) == 0 {
			return nil, termRecordDomainsAreNotScalarWitnessLeaves
		}
		return values[0], ""
	case termNumericInterval:
		return intervalEnvelopeWitness(descriptor)
	default:
		return nil, termRecordDomainsAreNotScalarWitnessLeaves
	}
}
func compareEnvelopeScalars(left, right any) int {
	category := func(value any) int {
		switch value.(type) {
		case bool:
			return 0
		case string:
			return 2
		default:
			return 1
		}
	}
	if result := cmp.Compare(category(left), category(right)); result != 0 {
		return result
	}
	render := func(value any) string {
		if text, ok := value.(string); ok {
			return text
		}
		raw, err := sortedJSON(value)
		if err != nil {
			return ""
		}
		return raw
	}
	return strings.Compare(render(left), render(right))
}
func intervalEnvelopeWitness(descriptor any) (any, string) {
	decoded, err := envelopeDomain(descriptor)
	if err != nil {
		return nil, termIntegerIntervalAdmitsNoWitnessValue
	}
	interval, ok := decoded.(domain.Interval)
	if !ok {
		return nil, termIntegerIntervalAdmitsNoWitnessValue
	}
	if interval.Type == domain.Integer {
		lower, _ := big.NewFloat(interval.Lower).Int(nil)
		upper, _ := big.NewFloat(interval.Upper).Int(nil)
		if !interval.LowerClosed {
			lower.Add(lower, big.NewInt(1))
		}
		order := lower.Cmp(upper)
		if order > 0 || order == 0 && !interval.UpperClosed {
			return nil, termIntegerIntervalAdmitsNoWitnessValue
		}
		return json.Number(lower.String()), ""
	}
	if interval.LowerClosed {
		return interval.Lower, ""
	}
	return (interval.Lower + interval.Upper) / 2, ""
}
func assignEnvelopePath(payload map[string]any, path string, value any) string {
	tokens := materializationOfferTokens(path)
	if len(tokens) == 0 {
		return "list-indexed paths are not supported for witness generation"
	}
	current := payload
	for index, token := range tokens {
		if strings.HasPrefix(token, "[") {
			return "list-indexed paths are not supported for witness generation"
		}
		if index == len(tokens)-1 {
			current[token] = value
			break
		}
		nested, ok := current[token].(map[string]any)
		if !ok {
			nested = map[string]any{}
			current[token] = nested
		}
		current = nested
	}
	return ""
}

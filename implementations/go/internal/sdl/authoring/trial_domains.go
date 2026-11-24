package authoring

import (
	"encoding/json"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// FiniteVariationOutcomes returns the existing domain's canonical trial outcomes.
// It checks cardinality before expanding an integer interval.
func (p *Parser) FiniteVariationOutcomes(document *Document, pointID string, maximum int) ([]byte, error) {
	if maximum < 1 || document == nil || !document.Validated() || document.contract != expandedContract {
		return nil, selectionInvalid()
	}
	for _, point := range document.semantic.variations {
		if point.name != pointID {
			continue
		}
		outcomes, err := finiteTrialOutcomes(point, maximum)
		if err != nil {
			return nil, err
		}
		return json.Marshal(outcomes)
	}
	return nil, selectionInvalid()
}

func trialDomainError(code string) error { return fault.New(fault.InvalidInput, code, nil) }

func finiteTrialOutcomes(point semanticVariation, maximum int) ([]json.RawMessage, error) {
	switch point.Kind {
	case variationParameterKind, termLogicalTiming:
		return finiteScalarTrialOutcomes(point.Domain, maximum)
	case termGovernedReference:
		return namedTrialOutcomes(point.Domain.Allowed, maximum, "reference", "reference_id")
	case variationAlternativeKind:
		names := make([]string, 0, len(point.Alternatives))
		for name := range point.Alternatives {
			names = append(names, name)
		}
		return namedTrialOutcomes(names, maximum, "member", "member_id")
	default:
		return nil, trialDomainError("trial-domain-kind-unsupported")
	}
}

func namedTrialOutcomes(names []string, maximum int, kind, field string) ([]json.RawMessage, error) {
	if len(names) == 0 {
		return nil, trialDomainError(codeTrialDomainEmpty)
	}
	if len(names) > maximum {
		return nil, trialDomainError(codeTrialDomainLimit)
	}
	ordered := slices.Clone(names)
	slices.Sort(ordered)
	output := make([]json.RawMessage, 0, len(ordered))
	for _, name := range ordered {
		raw, err := json.Marshal(map[string]string{kindField: kind, field: name})
		if err != nil {
			return nil, err
		}
		output = append(output, raw)
	}
	return output, nil
}

type trialScalarOutcome struct {
	key string
	raw json.RawMessage
}

func finiteScalarTrialOutcomes(domain semanticVariationDomain, maximum int) ([]json.RawMessage, error) {
	values, finite := domain.finite()
	if !finite {
		if domain.Kind != variationNumericKind || domain.Numeric != integerType {
			return nil, trialDomainError("trial-domain-not-finite")
		}
		return integerTrialOutcomes(domain, maximum)
	}
	if len(values) == 0 {
		return nil, trialDomainError(codeTrialDomainEmpty)
	}
	if len(values) > maximum {
		return nil, trialDomainError(codeTrialDomainLimit)
	}
	rows := make([]trialScalarOutcome, 0, len(values))
	for _, value := range values {
		raw, err := json.Marshal(map[string]any{kindField: termLiteral, valueField: value})
		if err != nil {
			return nil, err
		}
		key, err := trialScalarKey(value)
		if err != nil {
			return nil, err
		}
		rows = append(rows, trialScalarOutcome{key: key, raw: raw})
	}
	slices.SortStableFunc(rows, func(a, b trialScalarOutcome) int { return strings.Compare(a.key, b.key) })
	output := make([]json.RawMessage, len(rows))
	for i, row := range rows {
		output[i] = row.raw
	}
	return output, nil
}

func trialScalarKey(value any) (string, error) {
	kind := stringType
	switch scalar := value.(type) {
	case nil:
		kind = nullType
	case bool:
		kind = booleanType
	case json.Number:
		kind = integerType
		if strings.ContainsAny(scalar.String(), ".eE") {
			kind = numberType
		}
	}
	raw, err := json.Marshal(map[string]any{"type": kind, valueField: value})
	if err != nil {
		return "", err
	}
	canonical, err := canonjson.JCS(raw)
	return string(canonical), err
}

func integerTrialOutcomes(domain semanticVariationDomain, maximum int) ([]json.RawMessage, error) {
	lo, hi := domain.integers()
	count := new(big.Int).Add(new(big.Int).Sub(hi, lo), big.NewInt(1))
	if count.Sign() <= 0 {
		return nil, trialDomainError(codeTrialDomainEmpty)
	}
	if !count.IsInt64() || count.Cmp(big.NewInt(int64(maximum))) > 0 {
		return nil, trialDomainError(codeTrialDomainLimit)
	}
	output := make([]json.RawMessage, 0, int(count.Int64()))
	for current := new(big.Int).Set(lo); current.Cmp(hi) <= 0; current.Add(current, big.NewInt(1)) {
		raw, err := json.Marshal(map[string]any{kindField: termLiteral, valueField: json.Number(current.String())})
		if err != nil {
			return nil, err
		}
		output = append(output, raw)
	}
	return output, nil
}

const (
	codeTrialDomainEmpty = "trial-domain-empty"
	codeTrialDomainLimit = "trial-domain-limit-exceeded"
)

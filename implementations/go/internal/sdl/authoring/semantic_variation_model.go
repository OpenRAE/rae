package authoring

import (
	"bytes"
	"encoding/json"
	"math"
	"math/big"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
)

type semanticVariation struct {
	name   string
	Kind   string `json:"kind"`
	Target struct {
		Kind     string `json:"kind"`
		Variable string `json:"variable"`
		Owner    string `json:"owner"`
		Slot     string `json:"slot"`
	} `json:"target"`
	Domain       semanticVariationDomain            `json:"domain"`
	Alternatives map[string]semanticVariationMember `json:"alternatives"`
	Members      map[string]semanticVariationMember `json:"members"`
	Minimum      int                                `json:"minimum"`
	Maximum      *int                               `json:"maximum"`
	Unit         string                             `json:"unit"`
	Precedence   []struct {
		Before string `json:"before"`
		After  string `json:"after"`
	} `json:"precedence"`
	FixedPositions map[string]int `json:"fixed_positions"`
}
type semanticVariationMember struct {
	Kind       string                      `json:"kind"`
	Present    *bool                       `json:"present"`
	Inventory  map[string][]string         `json:"inventory"`
	References []string                    `json:"references"`
	Consumers  []semanticConsumerSelector  `json:"consumers"`
	Reference  string                      `json:"reference"`
	Requires   []semanticSelectionRelation `json:"requires"`
	Excludes   []semanticSelectionRelation `json:"excludes"`
}
type semanticSelectionRelation struct {
	Point   string   `json:"point"`
	Members []string `json:"members"`
}
type semanticVariationDomain struct {
	Kind        string            `json:"kind"`
	Value       json.RawMessage   `json:"value"`
	Values      []json.RawMessage `json:"values"`
	Allowed     []string          `json:"allowed_refs"`
	Numeric     string            `json:"numeric_type"`
	Lower       float64           `json:"lower"`
	Upper       float64           `json:"upper"`
	LowerClosed *bool             `json:"lower_closed"`
	UpperClosed *bool             `json:"upper_closed"`
}
type semanticVariationVariable struct {
	Type    string            `json:"type"`
	Allowed []json.RawMessage `json:"allowed_values"`
}

func (m *semanticModel) variationFacts() error {
	m.variationConsumerFacts()
	for _, name := range m.keys(variationPointsField) {
		var point semanticVariation
		if json.Unmarshal(fieldValue(m.transport.VariationPoints)[name], &point) != nil {
			return invalid()
		}
		point.name = name
		m.variations = append(m.variations, point)
	}
	m.variationVariables = map[string]semanticVariationVariable{}
	for name, raw := range fieldValue(m.transport.Variables) {
		var variable semanticVariationVariable
		if json.Unmarshal(raw, &variable) != nil {
			return invalid()
		}
		m.variationVariables[name] = variable
	}
	return nil
}
func variationScalar(raw json.RawMessage) any {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var scalar any
	if decoder.Decode(&scalar) != nil {
		return nil
	}
	return scalar
}
func (d semanticVariationDomain) finite() ([]any, bool) {
	switch d.Kind {
	case exactTerm:
		return []any{variationScalar(d.Value)}, true
	case "enum":
		values := make([]any, len(d.Values))
		for i, raw := range d.Values {
			values[i] = variationScalar(raw)
		}
		return values, true
	case booleanType:
		if len(d.Value) == 0 || string(d.Value) == nullType {
			return []any{false, true}, true
		}
		return []any{variationScalar(d.Value)}, true
	default:
		return nil, false
	}
}
func (d semanticVariationDomain) integers() (*big.Int, *big.Int) {
	lower, upper := math.Ceil(d.Lower), math.Floor(d.Upper)
	lo, _ := big.NewFloat(lower).Int(nil)
	hi, _ := big.NewFloat(upper).Int(nil)
	if d.LowerClosed != nil && !*d.LowerClosed && lower == d.Lower {
		lo.Add(lo, big.NewInt(1))
	}
	if d.UpperClosed != nil && !*d.UpperClosed && upper == d.Upper {
		hi.Sub(hi, big.NewInt(1))
	}
	return lo, hi
}
func (d semanticVariationDomain) hasMember() bool {
	if values, finite := d.finite(); finite {
		return len(values) > 0
	}
	if d.Kind != variationNumericKind {
		return false
	}
	if d.Numeric == numberType {
		return true
	}
	lo, hi := d.integers()
	return lo.Cmp(hi) <= 0
}
func variationType(value any, kind string) bool {
	switch scalar := value.(type) {
	case string:
		return kind == stringType
	case bool:
		return kind == booleanType
	case json.Number:
		return kind == numberType || kind == integerType && !strings.ContainsAny(string(scalar), ".eE")
	default:
		return false
	}
}
func (d semanticVariationDomain) matches(kind string) bool {
	if values, finite := d.finite(); finite {
		for _, value := range values {
			if !variationType(value, kind) {
				return false
			}
		}
		return true
	}
	return d.Kind == variationNumericKind && (kind == numberType || kind == integerType && d.Numeric == integerType)
}
func (v semanticVariationVariable) permits(d semanticVariationDomain) bool {
	if len(v.Allowed) == 0 {
		return true
	}
	values, finite := d.finite()
	if !finite {
		if d.Kind != variationNumericKind || d.Numeric != integerType {
			return false
		}
		lo, hi := d.integers()
		count := new(big.Int).Add(new(big.Int).Sub(hi, lo), big.NewInt(1))
		if !count.IsInt64() || count.Int64() > int64(len(v.Allowed)) {
			return false
		}
		for current := new(big.Int).Set(lo); current.Cmp(hi) <= 0; current.Add(current, big.NewInt(1)) {
			values = append(values, json.Number(current.String()))
		}
	}
	for _, candidate := range values {
		if !v.contains(candidate) {
			return false
		}
	}
	return true
}
func (v semanticVariationVariable) contains(candidate any) bool {
	for _, raw := range v.Allowed {
		if domain.Equal(variationScalar(raw), candidate) {
			return true
		}
	}
	return false
}

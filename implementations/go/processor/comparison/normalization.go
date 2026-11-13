package comparison

import (
	"bytes"
	_ "embed" // Required by the go:embed directive for native owner metadata.
	"encoding/json"
	"sync"
)

// ownerNormalization records only missing factory defaults, serializer omissions,
// and native child ownership. Published schemas remain the shape/default owner.
//
//go:embed owner-normalization.json
var ownerNormalization []byte

type normalizationChild struct {
	Model        string               `json:"model"`
	Items        *normalizationChild  `json:"items"`
	Values       *normalizationChild  `json:"values"`
	Alternatives []normalizationChild `json:"alternatives"`
}
type normalizationField struct {
	Child   *normalizationChild `json:"child"`
	Factory json.RawMessage     `json:"factory"`
	Omit    json.RawMessage     `json:"omit"`
}
type normalizationModel struct {
	Fields   map[string]normalizationField `json:"fields"`
	Literals map[string][]json.RawMessage  `json:"literals"`
	Required []string                      `json:"required"`
}
type normalizationMetadata struct {
	Models map[string]normalizationModel `json:"models"`
}

var normalizationRules = sync.OnceValues(func() (normalizationMetadata, error) { //nolint:gochecknoglobals // Read-only owner metadata is decoded once.
	var result normalizationMetadata
	err := decode(ownerNormalization, &result)
	return result, err
})

type normalizationWork struct {
	rules     normalizationMetadata
	remaining int
}

func normalizeOwner(model string, document any) (map[string]any, error) {
	rules, err := normalizationRules()
	if err != nil {
		return nil, err
	}
	root, ok := document.(map[string]any)
	if !ok {
		return nil, invalid()
	}
	work := normalizationWork{rules: rules, remaining: 100000}
	if err := work.model(model, root, 0); err != nil {
		return nil, err
	}
	return root, nil
}
func (w *normalizationWork) spend(depth int) error {
	w.remaining--
	if w.remaining < 0 || depth > 64 {
		return invalid()
	}
	return nil
}
func (w *normalizationWork) model(name string, document map[string]any, depth int) error {
	if err := w.spend(depth); err != nil {
		return err
	}
	rule, exists := w.rules.Models[name]
	if !exists {
		return invalid()
	}
	for field, normalizer := range rule.Fields {
		if err := w.field(field, normalizer, document, depth); err != nil {
			return err
		}
	}
	return nil
}
func (w *normalizationWork) field(name string, rule normalizationField, document map[string]any, depth int) error {
	if err := w.spend(depth); err != nil {
		return err
	}
	input, present := document[name]
	if !present && rule.Factory != nil {
		if decode(rule.Factory, &input) != nil {
			return invalid()
		}
		document[name] = input
		present = true
	}
	if !present {
		return nil
	}
	if rule.Child != nil && input != nil {
		if err := w.child(*rule.Child, input, depth+1); err != nil {
			return err
		}
	}
	if rule.Omit != nil {
		raw, err := json.Marshal(input)
		if err != nil {
			return invalid()
		}
		if bytes.Equal(raw, rule.Omit) {
			delete(document, name)
		}
	}
	return nil
}
func (w *normalizationWork) child(rule normalizationChild, input any, depth int) error {
	if err := w.spend(depth); err != nil {
		return err
	}
	if rule.Model != "" {
		if object, ok := input.(map[string]any); ok {
			return w.model(rule.Model, object, depth)
		}
		return nil
	}
	if rule.Items != nil {
		return w.items(*rule.Items, input, depth)
	}
	if rule.Values != nil {
		return w.values(*rule.Values, input, depth)
	}
	for _, alternative := range rule.Alternatives {
		if w.matches(alternative, input) {
			return w.child(alternative, input, depth)
		}
	}
	return nil
}
func (w *normalizationWork) items(rule normalizationChild, input any, depth int) error {
	for _, child := range array(input) {
		if err := w.child(rule, child, depth+1); err != nil {
			return err
		}
	}
	return nil
}
func (w *normalizationWork) values(rule normalizationChild, input any, depth int) error {
	for _, child := range object(input) {
		if err := w.child(rule, child, depth+1); err != nil {
			return err
		}
	}
	return nil
}
func (w *normalizationWork) matches(rule normalizationChild, input any) bool {
	if rule.Model == "" {
		return rule.Items != nil && isArray(input) || rule.Values != nil && isObject(input)
	}
	object, ok := input.(map[string]any)
	if !ok {
		return false
	}
	model := w.rules.Models[rule.Model]
	for _, name := range model.Required {
		if _, ok := object[name]; !ok {
			return false
		}
	}
	return matchesLiterals(model, object)
}
func matchesLiterals(model normalizationModel, object map[string]any) bool {
	for name, allowed := range model.Literals {
		input, present := object[name]
		if !present {
			continue
		}
		raw, err := json.Marshal(input)
		if err != nil {
			return false
		}
		matched := false
		for _, literal := range allowed {
			matched = matched || bytes.Equal(raw, literal)
		}
		if !matched {
			return false
		}
	}
	return true
}
func isArray(input any) bool  { _, ok := input.([]any); return ok }
func isObject(input any) bool { _, ok := input.(map[string]any); return ok }

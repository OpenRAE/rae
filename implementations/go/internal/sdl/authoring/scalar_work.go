package authoring

import (
	"encoding/json"
	"strings"
)

type fieldValueKey struct {
	pointer, name, value string
	number               bool
}
type textValueKey struct {
	value   string
	hyphens bool
	upper   bool
}

// Only immutable scalar results are shared. Arrays and model maps retain their
// independent construction; caches never retain source paths or error objects.
func (w *normalizer) shareScalar(value any) (any, error) {
	var raw string
	switch v := value.(type) {
	case string:
		raw = v
	case json.Number:
		raw = string(v)
	default:
		return value, nil
	}
	if w.scalars == nil {
		w.scalars = map[string]string{}
		w.scalarRemaining = w.workingLimit
	}
	retained, present := w.scalars[raw]
	if !present {
		if int64(len(raw)) > w.scalarRemaining {
			return nil, invalid()
		}
		w.scalarRemaining -= int64(len(raw))
		w.scalars[raw] = raw
		retained = raw
	}
	if _, number := value.(json.Number); number {
		return json.Number(retained), nil
	}
	return retained, nil
}
func (w *normalizer) memoField(pointer, name string, value any) (any, error) {
	key := fieldValueKey{pointer: pointer, name: name}
	switch v := value.(type) {
	case string:
		key.value = v
	case json.Number:
		key.value = string(v)
		key.number = true
	default:
		return w.fieldInput(pointer, name, value)
	}
	if cached, present := w.fields[key]; present {
		return cached, nil
	}
	result, err := w.fieldInput(pointer, name, value)
	if err != nil {
		return nil, err
	}
	switch result.(type) {
	case string, json.Number, bool, float64, nil:
		result, err = w.shareScalar(result)
		if err != nil {
			return nil, err
		}
		if w.fields == nil {
			w.fields = map[fieldValueKey]any{}
		}
		w.fields[key] = result
	}
	return result, nil
}
func (w *normalizer) caseText(value string, hyphens bool) (string, error) {
	key := textValueKey{value: value, hyphens: hyphens}
	return w.casedText(key)
}
func (w *normalizer) casedText(key textValueKey) (string, error) {
	if cached, present := w.casing[key]; present {
		return cached, nil
	}
	var normalized string
	if key.upper {
		normalized = upper(pythonTrim(key.value))
	} else {
		normalized = lower(key.value)
	}
	if key.hyphens {
		normalized = strings.ReplaceAll(normalized, "-", "_")
	}
	shared, err := w.shareScalar(normalized)
	if err != nil {
		return "", err
	}
	result := text(shared)
	if w.casing == nil {
		w.casing = map[textValueKey]string{}
	}
	w.casing[key] = result
	return result, nil
}

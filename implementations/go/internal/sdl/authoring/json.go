package authoring

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
)

// Model checks see all supplied fields. Only presentation omits serializer fields.
func encode(value any, limit int64, omit bool) ([]byte, error) {
	if err := checkJSONSize(value, limit, omit); err != nil {
		return nil, err
	}
	writer := jsonWriter{limit: limit, omit: omit}
	if err := writer.value(value); err != nil {
		return nil, err
	}
	return writer.out.Bytes(), nil
}

type jsonWriter struct {
	out   bytes.Buffer
	limit int64
	omit  bool
}

func (w *jsonWriter) append(raw []byte) error {
	if int64(len(raw)) > w.limit-int64(w.out.Len()) {
		return invalid()
	}
	_, _ = w.out.Write(raw)
	return nil
}
func (w *jsonWriter) value(value any) error {
	switch v := value.(type) {
	case ordered:
		return w.object(v)
	case map[string]any:
		entries := make(ordered, 0, len(v))
		for _, name := range slices.Sorted(maps.Keys(v)) {
			entries = append(entries, field{name: name, value: v[name]})
		}
		return w.object(entries)
	case []any:
		return w.sequence(v)
	case float64:
		normalized, err := normalizeFloat(v)
		if err != nil {
			return err
		}
		number, ok := normalized.(json.Number)
		if !ok {
			return invalid()
		}
		return w.append([]byte(number))
	default:
		raw, err := jsonScalar(value)
		if err != nil {
			return err
		}
		return w.append(raw)
	}
}
func (w *jsonWriter) object(entries ordered) error {
	if err := w.append([]byte{'{'}); err != nil {
		return err
	}
	first := true
	for _, entry := range entries {
		if w.omit && entry.omit {
			continue
		}
		if !first {
			if err := w.append([]byte{','}); err != nil {
				return err
			}
		}
		first = false
		if err := w.entry(entry); err != nil {
			return err
		}
	}
	return w.append([]byte{'}'})
}
func (w *jsonWriter) sequence(items []any) error {
	if err := w.append([]byte{'['}); err != nil {
		return err
	}
	for i, item := range items {
		if i > 0 {
			if err := w.append([]byte{','}); err != nil {
				return err
			}
		}
		if err := w.value(item); err != nil {
			return err
		}
	}
	return w.append([]byte{']'})
}

// Internal JSON preserves string bytes rather than applying HTML presentation escapes.
func jsonScalar(value any) ([]byte, error) {
	var out bytes.Buffer
	encoder := json.NewEncoder(&out)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(out.Bytes(), []byte{'\n'}), nil
}

func (w *jsonWriter) entry(entry field) error {
	name, err := jsonScalar(entry.name)
	if err != nil {
		return err
	}
	if err = w.append(append(name, ':')); err != nil {
		return err
	}
	return w.value(entry.value)
}

// The lower bound counts shared strings on every occurrence without copying
// them. Escaping can only increase this size; the writer enforces actual bytes.
func checkJSONSize(value any, limit int64, omit bool) error {
	remaining := limit
	return jsonMinimum(value, &remaining, omit)
}
func reserveJSON(remaining *int64, count int64) error {
	if count < 0 || count > *remaining {
		return invalid()
	}
	*remaining -= count
	return nil
}
func jsonMinimum(value any, remaining *int64, omit bool) error {
	switch v := value.(type) {
	case string:
		if err := reserveJSON(remaining, int64(len(v))); err != nil {
			return err
		}
		return reserveJSON(remaining, 2)
	case ordered:
		return jsonObjectMinimum(v, remaining, omit)
	case map[string]any:
		return jsonMapMinimum(v, remaining, omit)
	case []any:
		if err := reserveJSON(remaining, 2); err != nil {
			return err
		}
		for _, child := range v {
			if err := jsonMinimum(child, remaining, omit); err != nil {
				return err
			}
		}
		return nil
	default:
		return reserveJSON(remaining, 1)
	}
}
func jsonObjectMinimum(entries ordered, remaining *int64, omit bool) error {
	if err := reserveJSON(remaining, 2); err != nil {
		return err
	}
	for _, entry := range entries {
		if omit && entry.omit {
			continue
		}
		if err := jsonMemberMinimum(entry.name, entry.value, remaining, omit); err != nil {
			return err
		}
	}
	return nil
}
func jsonMemberMinimum(name string, value any, remaining *int64, omit bool) error {
	if err := jsonMinimum(name, remaining, omit); err != nil {
		return err
	}
	if err := reserveJSON(remaining, 1); err != nil {
		return err
	}
	return jsonMinimum(value, remaining, omit)
}

func jsonMapMinimum(v map[string]any, remaining *int64, omit bool) error {
	if err := reserveJSON(remaining, 2); err != nil {
		return err
	}
	for name, child := range v {
		if err := jsonMemberMinimum(name, child, remaining, omit); err != nil {
			return err
		}
	}
	return nil
}

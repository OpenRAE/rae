package authoring

import (
	"bytes"
	"encoding/json"
)

// Model checks see all supplied fields. Only presentation omits serializer fields.
func encode(value any, limit int64, omit bool) ([]byte, error) {
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

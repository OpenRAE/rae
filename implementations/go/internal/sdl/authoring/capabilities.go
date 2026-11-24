package authoring

import "regexp"

var capabilityName = regexp.MustCompile(`^CAP_[A-Z0-9_]+\z`)

func (w *normalizer) capability(value any) (any, error) {
	s, ok := value.(string)
	if !ok {
		return nil, invalid()
	}
	normalized, err := w.casedText(textValueKey{value: s, hyphens: true, upper: true})
	if err != nil {
		return nil, err
	}
	if !capabilityName.MatchString(normalized) {
		return nil, invalid()
	}
	return normalized, nil
}

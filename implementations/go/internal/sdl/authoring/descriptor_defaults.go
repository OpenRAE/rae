package authoring

import "maps"

func (q *scopeQueries) descriptorDefaults(value map[string]any, definition string) (map[string]any, error) {
	pointer := "#/$defs/" + definition
	schema := object(object(q.w.parser.schemas[q.w.id]["$defs"])[definition])
	result := maps.Clone(value)
	for field, raw := range object(schema["properties"]) {
		if _, present := result[field]; present {
			continue
		}
		fallback, found, err := q.defaultValue(pointer, field, object(raw))
		if err != nil {
			return nil, err
		}
		if found {
			result[field] = fallback
		}
	}
	return result, nil
}

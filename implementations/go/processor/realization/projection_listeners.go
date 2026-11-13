package realization

import (
	"slices"
	"strings"
)

func projectListeners(value any, recursive bool) ([]any, error) {
	items, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	result := make([]any, 0, len(items))
	for _, item := range items {
		record, ok := item.(map[string]any)
		if !ok {
			return nil, invalidRealization()
		}
		id, ok := record["service_listener_id"].(string)
		if !ok || id == "" {
			return nil, invalidRealization()
		}
		normalized, err := normalizeConcernValue(termServiceListeners, []any{record})
		if err != nil {
			return nil, err
		}
		row := ownedProjection[map[string]any](ownedProjection[[]any](normalized)[0])
		entry := map[string]any{}
		for _, field := range []string{"service_listener_id", "service", termAddress, "port", termProtocol, "address_family", termScope, "bind_interface", "socket_path", "process_ref", "process_name"} {
			if _, supplied := record[field]; supplied {
				entry[field] = row[field]
			}
		}
		result = append(result, entry)
	}
	if !recursive {
		slices.SortStableFunc(result, func(a, b any) int {
			return strings.Compare(ownedProjection[string](ownedProjection[map[string]any](a)["service_listener_id"]), ownedProjection[string](ownedProjection[map[string]any](b)["service_listener_id"]))
		})
	}
	return result, nil
}

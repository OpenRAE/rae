package realization

import (
	"encoding/json"
	"slices"
	"strings"
)

func scalarSortText(value any) (string, error) {
	switch item := value.(type) {
	case nil:
		return "None", nil
	case string:
		return item, nil
	case json.Number:
		return string(item), nil
	case bool:
		if item {
			return "True", nil
		}
		return "False", nil
	default:
		return "", invalidRealization()
	}
}

func projectPorts(value any, recursive bool) ([]any, error) {
	items, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	output := make([]any, 0, len(items))
	keys := []string{termHostIP, termHostPort, "container_port", termProtocol}
	for _, item := range items {
		entry, err := projectPort(item, keys)
		if err != nil {
			return nil, err
		}

		output = append(output, entry)
	}
	if !recursive {
		slices.SortStableFunc(output, func(a, b any) int {
			left, right := ownedProjection[map[string]any](a), ownedProjection[map[string]any](b)
			for _, key := range keys {
				l, _ := scalarSortText(left[key])
				r, _ := scalarSortText(right[key])
				if order := strings.Compare(l, r); order != 0 {
					return order
				}
			}
			return 0
		})
	}
	return output, nil
}

func projectPort(item any, keys []string) (map[string]any, error) {
	record, ok := item.(map[string]any)
	if !ok {
		return nil, invalidRealization()
	}
	entry := map[string]any{termHostIP: fieldDefault(record, termHostIP, ""), termHostPort: record[termHostPort], "container_port": record["container_port"], termProtocol: fieldDefault(record, termProtocol, "tcp")}
	for _, key := range keys {
		if _, err := scalarSortText(entry[key]); err != nil {
			return nil, err
		}
	}
	return entry, nil
}

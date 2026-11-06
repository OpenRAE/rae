package admission

import (
	"encoding/json"
	"strconv"
	"testing"
)

type referenceChange struct {
	Path  []string        `json:"path"`
	Value json.RawMessage `json:"value"`
}

func applyReferenceChange(t *testing.T, root any, change referenceChange) {
	t.Helper()
	if len(change.Path) == 0 {
		t.Fatal("missing independent reference change path")
	}
	parent := root
	for _, token := range change.Path[:len(change.Path)-1] {
		if items, ok := parent.([]any); ok {
			parent = items[referenceIndex(t, token, len(items))]
		} else {
			parent = object(parent)[token]
		}
	}
	value := decodeRuleObject(t, string(change.Value))
	key := change.Path[len(change.Path)-1]
	if items, ok := parent.([]any); ok {
		items[referenceIndex(t, key, len(items))] = value
	} else if fields := object(parent); fields != nil {
		fields[key] = value
	} else {
		t.Fatal("independent reference parent is missing")
	}
}

func referenceIndex(t *testing.T, token string, size int) int {
	t.Helper()
	index, err := strconv.Atoi(token)
	if err != nil || index < 0 || index >= size {
		t.Fatal("independent reference array position is missing")
	}
	return index
}

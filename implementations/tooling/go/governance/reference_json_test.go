package governance

import (
	"encoding/json"
	"strconv"
	"strings"
	"testing"
)

type referenceJSONEdit struct {
	Path   []string        `json:"Path"`
	Value  json.RawMessage `json:"Value"`
	Delete bool            `json:"Delete"`
}

func referenceJSONEdits(t *testing.T, base map[string]string, edits map[string][]referenceJSONEdit) map[string]*string {
	t.Helper()
	changes := map[string]*string{}
	for name, steps := range edits {
		value := referenceJSONValue(t, []byte(base[name]))
		for _, step := range steps {
			value = referenceJSONStep(t, value, step)
		}
		data, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		text := string(data)
		changes[name] = &text
	}
	return changes
}
func referenceJSONValue(t *testing.T, data []byte) any {
	t.Helper()
	decoder := json.NewDecoder(strings.NewReader(string(data)))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		t.Fatal(err)
	}
	return value
}
func referenceJSONStep(t *testing.T, value any, edit referenceJSONEdit) any {
	t.Helper()
	if len(edit.Path) == 0 {
		return referenceJSONValue(t, edit.Value)
	}
	node := value
	for _, part := range edit.Path[:len(edit.Path)-1] {
		switch parent := node.(type) {
		case map[string]any:
			node = parent[part]
		case []any:
			index, err := strconv.Atoi(part)
			if err != nil {
				t.Fatal(err)
			}
			node = parent[index]
		default:
			t.Fatal("recorded JSON edit traverses a scalar")
		}
	}
	leaf := edit.Path[len(edit.Path)-1]
	switch parent := node.(type) {
	case map[string]any:
		if edit.Delete {
			delete(parent, leaf)
		} else {
			parent[leaf] = referenceJSONValue(t, edit.Value)
		}
	case []any:
		index, err := strconv.Atoi(leaf)
		if err != nil {
			t.Fatal(err)
		}
		if edit.Delete {
			t.Fatal("recorded array deletion needs a replacement recipe")
		}
		parent[index] = referenceJSONValue(t, edit.Value)
	default:
		t.Fatal("recorded JSON edit targets a scalar")
	}
	return value
}

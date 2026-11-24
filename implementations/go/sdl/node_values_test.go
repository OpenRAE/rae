package sdl_test

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestNodeValueConstructionRetainsNativeDefaultsAndTypedPresence(t *testing.T) {
	raw, err := os.ReadFile("testdata/node-values.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name       string              `json:"name"`
		Source     map[string]any      `json:"source"`
		Normalized json.RawMessage     `json:"normalized"`
		Presence   map[string][]string `json:"presence"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&cases); err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			normalized, presence, err := sdl.NormalizeNodeValue(nodeContextFragment(t, test.Source))
			if err != nil {
				t.Fatal(err)
			}
			if !equalDescriptorJSON(t, descriptorJSON(t, normalized.Document()), test.Normalized) {
				t.Fatalf("whole node normalization differs: got=%s want=%s", descriptorJSON(t, normalized.Document()), test.Normalized)
			}
			if !cmp.Equal(presence, test.Presence) {
				t.Fatalf("typed presence=%v want=%v", presence, test.Presence)
			}
		})
	}
}

func TestNodeValueConstructionRejectsForeignAndUnknownFields(t *testing.T) {
	input := nodeContextFragment(t, map[string]any{"type": "compute"})
	if _, _, err := sdl.NormalizeNodeValue(foreignFragment{input}); err == nil {
		t.Fatal("foreign node value admitted")
	}
	for _, member := range []string{"data", "value_present", "unknown"} {
		invalid := nodeContextFragment(t, map[string]any{"type": "compute", member: true})
		if _, _, err := sdl.NormalizeNodeValue(invalid); err == nil {
			t.Fatalf("unknown node field %s admitted", member)
		}
	}
}

package sdl_test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestNodeValueConstructionRefusesMalformedComparisonInputsWithoutEcho(t *testing.T) {
	for _, test := range []struct {
		name  string
		value any
	}{
		{"null", nil},
		{"sequence", []any{}},
		{"text", "private-node-comparison-canary"},
		{"invalid-type", map[string]any{"type": json.Number("7")}},
	} {
		t.Run(test.name, func(t *testing.T) {
			normalized, presence, err := sdl.NormalizeNodeValue(nodeContextFragment(t, test.value))
			if err == nil || normalized != nil || len(presence) != 0 {
				t.Fatal("malformed comparison node became native authority")
			}
			if strings.Contains(err.Error(), "private-node-comparison-canary") {
				t.Fatal("comparison input appeared in the refusal")
			}
		})
	}
}

package authoring

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestNullableIntegerConstructionPreservesRequiredBounds(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, row := range []struct {
		name, body string
		accepted   bool
	}{
		{"optional-null", "conditions: {health: {command: /bin/true, interval: 15, timeout: null, retries: null, start_period: null}}", true},
		{"optional-positive", "conditions: {health: {command: /bin/true, interval: 15, timeout: 1}}", true},
		{"optional-zero", "conditions: {health: {command: /bin/true, interval: 15, timeout: 0}}", false},
		{"required-null", "nodes: {host: {type: compute, resources: {ram: 1 GiB, cpu: null}}}", false},
	} {
		t.Run(row.name, func(t *testing.T) {
			_, err := parser.Decode(Request{Source: []byte("name: bounds\n" + row.body + "\n")})
			if (err == nil) != row.accepted {
				t.Fatalf("construction = %v; want accepted %v", err, row.accepted)
			}
		})
	}
}

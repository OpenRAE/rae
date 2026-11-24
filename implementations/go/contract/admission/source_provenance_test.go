package admission

import (
	"encoding/json"
	"maps"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestResolvedImportProvenanceModel(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	base := map[string]any{"namespace": []any{"demo"}, "requested_source": "local:module.yaml", "requested_version": "*", "module_id": "example/demo", "module_version": "1", "resolved_source": "module.yaml"}
	cases := []struct {
		name, field string
		value       any
		valid       bool
	}{
		{"valid", "module_id", "example/demo", true},
		{"absolute", "requested_source", "local:/workspace/module.yaml", false},
		{"drive", "requested_source", `local:C:\module.yaml`, false},
		{"userinfo", "requested_source", "oci:user:credential@example.test/module", false},
		{"module", "module_id", "Example/demo", false},
		{"digest", "requested_digest", strings.Repeat("a", 64), false},
		{"prefixed-digest", "requested_digest", "sha256:" + strings.Repeat("a", 64), true},
		{"local-binding", "bindings", []any{map[string]any{"parameter": []any{"v"}, "origin": "default", "value": 1}}, true},
		{"qualified-binding", "bindings", []any{map[string]any{"parameter": []any{"demo", "v"}, "origin": "default", "value": 1}}, false},
		{"duplicate-binding", "bindings", []any{map[string]any{"parameter": []any{"v"}, "origin": "default", "value": 1}, map[string]any{"parameter": []any{"v"}, "origin": "provided", "value": 2}}, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			value := maps.Clone(base)
			value[c.field] = c.value
			raw, err := json.Marshal(value)
			if err != nil {
				t.Fatal(err)
			}
			err = owner.CheckModelFragment("instantiated-scenario-v1", "#/$defs/ResolvedImportProvenance", raw, ingress.Limits{MaxBytes: 4096, MaxDepth: 16})
			if (err == nil) != c.valid {
				t.Fatalf("valid=%v, want %v: %v", err == nil, c.valid, err)
			}
		})
	}
}

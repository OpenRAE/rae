package authoring

import "testing"

func TestMigrationOpenPostureUsesOnlyTheMostSpecificLocalScope(t *testing.T) {
	for _, test := range []struct {
		name, fallback, pointer string
		scopes                  []any
		want                    bool
	}{
		{"default open", "open", "/nodes/host", nil, true},
		{"unspecified default", "unspecified", "/nodes/host", nil, false},
		{"child open", "closed", "/nodes/host", []any{map[string]any{"field_pointer": "/nodes", "posture": "open"}}, true},
		{"child closes", "open", "/nodes/host", []any{map[string]any{"field_pointer": "/nodes", "posture": "open"}, map[string]any{"field_pointer": "/nodes/host", "posture": "closed"}}, false},
		{"sibling is independent", "closed", "/nodes/host", []any{map[string]any{"field_pointer": "/nodes/other", "posture": "open"}}, false},
		{"namespace is independent", "closed", "/nodes/host", []any{map[string]any{"namespace": []any{"imported"}, "field_pointer": "/nodes", "posture": "open"}}, false},
		{"unspecified does not override", "open", "/nodes/host", []any{map[string]any{"field_pointer": "/nodes", "posture": "unspecified"}}, true},
		{"later broad rule cannot widen", "closed", "/nodes/host", []any{map[string]any{"field_pointer": "/nodes/host", "posture": "closed"}, map[string]any{"field_pointer": "", "posture": "open"}}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			root := map[string]any{"realization": map[string]any{"default": test.fallback, "scopes": test.scopes}}
			if explicitOpenRealization(root, test.pointer) != test.want {
				t.Fatalf("migration posture changed for %s", test.pointer)
			}
		})
	}
	if explicitOpenRealization(map[string]any{}, "/nodes") {
		t.Fatal("missing designation invented openness")
	}
}

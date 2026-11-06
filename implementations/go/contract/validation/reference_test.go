package validation

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestReferenceBindingPublishedPathsAndKeyFields(t *testing.T) {
	v, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		id, pointer, path string
		fields            []string
		valid             bool
	}{
		{"sdl-authoring-input-v1", "#/$defs/Node", "nodes.*", []string{"type", "source", "services"}, true},
		{"sdl-authoring-input-v1", "#/$defs/RuntimeConfiguration", "nodes.*.runtime", []string{"environment"}, true},
		{"instantiated-scenario-v1", "#/$defs/Node", "nodes.*", []string{"type"}, true},
		{"unknown", "#/$defs/Node", "nodes.*", []string{"type"}, false},
		{"sdl-authoring-input-v1", "#/$defs/Absent", "nodes.*", []string{"type"}, false},
		{"sdl-authoring-input-v1", "#/$defs/Node", "accounts.*", []string{"type"}, false},
		{"sdl-authoring-input-v1", "#/$defs/Node", "nodes.*", []string{"missing"}, false},
		{"sdl-authoring-input-v1", "#/$defs/Node", "nodes.*", []string{"type", "type"}, false},
		{"sdl-authoring-input-v1", "https://example.test/schema", "nodes.*", []string{"type"}, false},
		{"sdl-authoring-input-v1", "#/$defs/Node", "nodes.*", nil, false},
		{"sdl-authoring-input-v1", "#/$defs/Node", "nodes.*.services.*", []string{"type"}, false},
		{"sdl-authoring-input-v1", "#/$defs/Node", "nodes.unknown", []string{"type"}, false},
	} {
		err := v.CheckReferenceBinding(test.id, test.pointer, test.path, test.fields)
		if (err == nil) != test.valid {
			t.Errorf("%s %s %s: admitted=%v, want %v", test.id, test.pointer, test.path, err == nil, test.valid)
		}
	}
	var zero *Validator
	if err := zero.CheckReferenceBinding("x", "#/x", "x", []string{"id"}); err == nil {
		t.Fatal("nil checker accepted binding")
	}
}
func TestReferenceLookupRefusesCyclesAndWorkExhaustion(t *testing.T) {
	root := map[string]any{"$defs": map[string]any{"a": map[string]any{"$ref": "#/$defs/b"}, "b": map[string]any{"$ref": "#/$defs/a"}}}
	lookup := referenceLookup{root, 100}
	if _, err := lookup.resolve(map[string]any{"$ref": "#/$defs/a"}); err == nil {
		t.Fatal("accepted reference cycle")
	}
	lookup = referenceLookup{root, 0}
	_, err := lookup.resolve(map[string]any{"type": "object"})
	if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
		t.Fatalf("unbounded lookup: %v", err)
	}
	lookup = referenceLookup{root, 100}
	if _, err = lookup.resolve(map[string]any{"$ref": true}); err == nil {
		t.Fatal("accepted non-string reference")
	}
}

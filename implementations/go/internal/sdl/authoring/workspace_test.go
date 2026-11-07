package authoring

import (
	"encoding/json"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestWorkspaceDiagnostic(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	raw := []byte("name: a\nimports: [{source: 'local:module.yaml', namespace: m}]\n")
	files := fstest.MapFS{"main.yaml": {Data: raw}, "module.yaml": {Data: []byte("name: m\nmodule: {id: p/m, version: '1'}\n")}, "raes-trust.yaml": {Data: []byte("allow_unsigned_local_sources: !!str true\n")}}
	_, err = parser.Format(Request{Name: "main.yaml", Source: raw, FS: files})
	diagnostics := source.Diagnostics(err)
	if len(diagnostics) != 1 || diagnostics[0].Code != "sdl.workspace-config.invalid" || diagnostics[0].Source != "raes-trust.yaml" || diagnostics[0].Range != (source.Range{Start: source.Position{Line: 1, Column: 31}, End: source.Position{Line: 1, Column: 36}}) {
		t.Fatalf("workspace diagnostic: %+v; error=%v", diagnostics, err)
	}
	diagnostics[0].Code = "changed"
	if source.Diagnostics(err)[0].Code != "sdl.workspace-config.invalid" {
		t.Fatal("caller changed diagnostic")
	}
}

// Pydantic's ordinary bool accepts numeric zero and one, without stripping
// surrounding whitespace from text. Custom SDL flag parsing is distinct.
func TestPrimitiveBooleanBoundary(t *testing.T) {
	for _, value := range []any{float64(1), json.Number("1.0"), json.Number("1e0")} {
		result, err := normalizeBoolean(value, false)
		if err != nil || result != true {
			t.Fatalf("ordinary bool %v: %v, %v", value, result, err)
		}
	}
	if _, err := normalizeBoolean(" true ", false); err == nil {
		t.Fatal("ordinary bool trimmed whitespace")
	}
	if result, err := normalizeBoolean(" true ", true); err != nil || result != true {
		t.Fatal("custom SDL flag lost its trimming rule")
	}
}

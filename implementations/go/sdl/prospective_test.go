package sdl_test

import (
	"bytes"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestProspectiveContentAdmitsCommonQualifiedContentWithoutPhaseAuthority(t *testing.T) {
	input := nodeContextFragment(t, map[string]any{"name": "prospective", "nodes": map[string]any{"mod.host": map[string]any{"type": "compute"}}, "infrastructure": map[string]any{"mod.host": map[string]any{}}})
	admitted, err := sdl.AdmitProspectiveContent(input)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := any(admitted).(sdl.Scenario); ok {
		t.Fatal("prospective content acquired source authority")
	}
	for _, read := range []func() []byte{admitted.JSON, admitted.ModelJSON} {
		first := read()
		if !bytes.Contains(first, []byte("mod.host")) {
			t.Fatal("qualified content missing")
		}
		first[0] = '!'
		if read()[0] != '{' {
			t.Fatal("caller mutated native content")
		}
	}
}

func TestProspectiveContentRefusesUnresolvedInvalidAndPhaseInputs(t *testing.T) {
	cases := []map[string]any{
		{"name": "prospective", "variables": map[string]any{}},
		{"name": "prospective", "variation_points": map[string]any{}},
		{"name": "prospective", "expansion_provenance": map[string]any{}},
		{"name": "prospective", "instantiation_provenance": map[string]any{}},
		{"name": "prospective", "module": nil},
		{"name": "prospective", "semantic_revision": "unknown"},
		{"name": "prospective", "nodes": map[string]any{"mod.host": map[string]any{"type": "compute", "resources": map[string]any{"cpu": "${cpu}"}}}},
		{"name": "prospective", "nodes": map[string]any{"mod..host": map[string]any{"type": "compute"}}},
		{"name": "prospective", "nodes": map[string]any{"host": map[string]any{"type": "compute", "runtime": map[string]any{"database_services": []any{map[string]any{"database_service_id": "db", "engine": "sqlite", "service": "absent"}}}}}},
	}
	for i, input := range cases {
		if _, err := sdl.AdmitProspectiveContent(nodeContextFragment(t, input)); err == nil {
			t.Fatalf("invalid case %d admitted", i)
		}
	}
	input := nodeContextFragment(t, map[string]any{"name": "prospective"})
	if _, err := sdl.AdmitProspectiveContent(foreignFragment{input}); err == nil {
		t.Fatal("foreign input admitted")
	}
}

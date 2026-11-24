package admission

import (
	"encoding/json"
	"strconv"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestSDLConstructionStage(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 128}
	raw := []byte(`{"name":"a","nodes":{"n":{"type":"compute","os_version":"22"}}}`)
	if err = owner.CheckSDLConstruction("sdl-authoring-input-v1", "#", raw, limits); err != nil {
		t.Fatal(err)
	}
	if owner.CheckPortable("sdl-authoring-input-v1", raw, limits) == nil {
		t.Fatal("construction changed published-contract checks")
	}
	cases := []struct {
		name, contract, pointer, data string
		valid                         bool
	}{
		{"authored-fragment", "sdl-authoring-input-v1", "#/$defs/Node", `{"type":"compute","os_version":"${v}"}`, true},
		{"materialized-fragment", "materialized-scenario-v1", "#/$defs/Node", `{"type":"compute","os_version":"22"}`, true},
		{"instantiated-fragment", "instantiated-scenario-v1", "#/$defs/Node", `{"type":"compute","os_version":"22"}`, true},
		{"unknown-member", "sdl-authoring-input-v1", "#/$defs/Node", `{"type":"compute","extra":1}`, false},
		{"bad-os-token", "sdl-authoring-input-v1", "#/$defs/Node", `{"type":"compute","os":"invalid"}`, false},
		{"unknown-contract", "instantiated-scenario-v1", "#", `{}`, false},
		{"unknown-fragment", "sdl-authoring-input-v1", "#/unknown", `{}`, false},
		{"missing-discriminator", "sdl-authoring-input-v1", "#/$defs/AlternativeVariationPoint", `{"target":{"owner":"x","slot":"content.target"},"alternatives":{"a":{"reference":"n"}}}`, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := owner.CheckSDLConstruction(c.contract, c.pointer, []byte(c.data), limits)
			if (err == nil) != c.valid {
				t.Fatalf("valid=%v, want %v: %v", err == nil, c.valid, err)
			}
		})
	}
	var zero *Validator
	if zero.CheckSDLConstruction("sdl-authoring-input-v1", "#", []byte(`{}`), limits) == nil {
		t.Fatal("nil owner accepted input")
	}
}

// The source profile permits 20,000 minimal nodes (80,005 source nodes).
// The unchanged reference formatter accepts this one targeted boundary input.
func TestSDLConstructionSourceWork(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	nodes := map[string]any{}
	for i := range 20000 {
		nodes["n"+strconv.Itoa(i)] = map[string]any{"type": "compute"}
	}
	raw, err := json.Marshal(map[string]any{"name": "a", "nodes": nodes})
	if err != nil {
		t.Fatal(err)
	}
	if err = owner.CheckSDLConstruction("sdl-authoring-input-v1", "#", raw, ingress.Limits{MaxBytes: len(raw), MaxDepth: 128}); err != nil {
		t.Fatal(err)
	}
}

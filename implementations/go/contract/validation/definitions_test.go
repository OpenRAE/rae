package validation

import (
	"bytes"
	"errors"
	"slices"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

const definitionsTestSchema = `{
	"$schema": "https://json-schema.org/draft/2020-12/schema",
	"title": "Root",
	"type": "object",
	"properties": {
		"choice": {"anyOf": [{"$ref": "#/$defs/Left"}, {"$ref": "#/$defs/Right"}, {"type": "null"}]},
		"loose": {"anyOf": [{"$ref": "#/$defs/Strict"}, {"$ref": "#/$defs/Open"}]},
		"items": {"type": "array", "items": {"$ref": "#/$defs/Leaf"}},
		"pair": {"type": "array", "prefixItems": [{"$ref": "#/$defs/Leaf"}, {"type": "string"}]},
		"named": {"type": "object", "additionalProperties": {"$ref": "#/$defs/Leaf"}},
		"single": {"allOf": [{"$ref": "#/$defs/Leaf"}]}
	},
	"$defs": {
		"Left": {"type": "object", "properties": {"kind": {"const": "left"}, "leaf": {"$ref": "#/$defs/Leaf"}}},
		"Right": {"type": "object", "properties": {"kind": {"enum": ["right", "other"]}}},
		"Strict": {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"], "additionalProperties": false},
		"Open": {"type": "object", "properties": {"b": {"type": "string"}}},
		"Leaf": {"type": "object", "properties": {"value": {"type": "string"}}}
	}
}`

func definitionsTestValidator(t *testing.T) *Validator {
	t.Helper()
	doc, err := jsonschema.UnmarshalJSON(bytes.NewBufferString(definitionsTestSchema))
	if err != nil {
		t.Fatal(err)
	}
	compiler := jsonschema.NewCompiler()
	compiler.UseLoader(offline{})
	if err = compiler.AddResource("urn:definitions", doc); err != nil {
		t.Fatal(err)
	}
	schema, err := compiler.Compile("urn:definitions")
	if err != nil {
		t.Fatal(err)
	}
	root, ok := doc.(map[string]any)
	if !ok {
		t.Fatal("test schema is not an object")
	}
	return &Validator{contracts: map[string]contract{"test": {schema: schema, raw: root}}}
}

func TestVisitDefinitionsTypesInnerInstancesFirst(t *testing.T) {
	v := definitionsTestValidator(t)
	data := []byte(`{"choice":{"kind":"left","leaf":{"value":"x"}},"loose":{"b":"y"},"items":[{"value":"1"},{"value":"2"}],"pair":[{"value":"p"},"s"],"named":{"k":{"value":"n"}},"single":{"value":"s"}}`)
	var visits []string
	root, err := v.VisitDefinitions("test", data, ingress.Limits{MaxBytes: 4096}, func(visit DefinitionVisit) error {
		visits = append(visits, visit.Definition+"@"+visit.Path)
		visit.Value["seen"] = true
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{"Leaf@/choice/leaf", "Left@/choice", "Leaf@/items/0", "Leaf@/items/1", "Open@/loose", "Leaf@/named/k", "Leaf@/pair/0", "Leaf@/single", "Root@"}
	if !slices.Equal(visits, want) {
		t.Fatalf("visits = %v, want %v", visits, want)
	}
	if seen, _ := root.(map[string]any)["seen"].(bool); !seen {
		t.Fatal("a visit could not change the returned root")
	}
}

func TestVisitDefinitionsSelectsUnionMembers(t *testing.T) {
	v := definitionsTestValidator(t)
	for name, test := range map[string]struct {
		data string
		want []string
	}{
		"constant":    {`{"choice":{"kind":"right"}}`, []string{"Right@/choice", "Root@"}},
		"enumeration": {`{"choice":{"kind":"other"}}`, []string{"Right@/choice", "Root@"}},
		"mismatch":    {`{"choice":{"kind":"none"}}`, []string{"Root@"}},
		"validates":   {`{"loose":{"a":"x"}}`, []string{"Strict@/loose", "Root@"}},
		"neither":     {`{"loose":{"a":1,"c":true}}`, []string{"Open@/loose", "Root@"}},
		"null":        {`{"choice":null}`, []string{"Root@"}},
	} {
		t.Run(name, func(t *testing.T) {
			var visits []string
			if _, err := v.VisitDefinitions("test", []byte(test.data), ingress.Limits{MaxBytes: 4096}, func(visit DefinitionVisit) error {
				visits = append(visits, visit.Definition+"@"+visit.Path)
				return nil
			}); err != nil {
				t.Fatal(err)
			}
			if !slices.Equal(visits, test.want) {
				t.Fatalf("visits = %v, want %v", visits, test.want)
			}
		})
	}
}

func TestVisitDefinitionsRefusesUnboundedOrUnownedInput(t *testing.T) {
	v := definitionsTestValidator(t)
	visit := func(DefinitionVisit) error { return nil }
	if _, err := v.VisitDefinitions("unknown", []byte(`{}`), ingress.Limits{MaxBytes: 16}, visit); err == nil {
		t.Error("visited an unknown contract")
	}
	if _, err := v.VisitDefinitions("test", []byte(`{}`), ingress.Limits{MaxBytes: 16}, nil); err == nil {
		t.Error("visited without a visit")
	}
	if _, err := (*Validator)(nil).VisitDefinitions("test", []byte(`{}`), ingress.Limits{MaxBytes: 16}, visit); err == nil {
		t.Error("a nil validator visited")
	}
	if _, err := v.VisitDefinitions("test", []byte(`{"items":[`), ingress.Limits{MaxBytes: 16}, visit); err == nil {
		t.Error("visited malformed input")
	}
	if _, err := v.VisitDefinitions("test", []byte(`{"choice":{"kind":"left","leaf":{}}}`), ingress.Limits{MaxBytes: 64, MaxDepth: 1}, visit); err == nil {
		t.Error("visited beyond the depth bound")
	}
	refusal := errors.New("refused")
	if _, err := v.VisitDefinitions("test", []byte(`{}`), ingress.Limits{MaxBytes: 16}, func(DefinitionVisit) error { return refusal }); err == nil || errors.Is(err, refusal) {
		t.Errorf("visit refusal = %v, want a redacted refusal", err)
	}
}

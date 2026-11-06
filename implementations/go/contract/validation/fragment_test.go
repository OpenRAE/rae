package validation

import (
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestDefaultedObjectFragmentPreservesInputAndBounds(t *testing.T) {
	source := sourceFixture()
	source["schemas/example.json"] = &fstest.MapFile{Data: []byte(`{"type":"object","properties":{"claim":{"$ref":"#/$defs/claim"}},"$defs":{"claim":{"type":"object","additionalProperties":false,"required":["id"],"properties":{"id":{"type":"string"},"mode":{"type":"string","default":"safe"}}}}}`)}
	v, err := load(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	raw := []byte(`{"id":"a"}`)
	limits := ingress.Limits{MaxBytes: 256, MaxDepth: 8}
	plain, err := v.DecodeObjectFragment("example", "#/$defs/claim", raw, limits)
	if err != nil {
		t.Fatal(err)
	}
	if _, present := plain["mode"]; present {
		t.Fatal("decode synthesized a model default")
	}
	first, err := v.DefaultedObjectFragment("example", "#/$defs/claim", raw, limits)
	if err != nil || first["mode"] != "safe" {
		t.Fatalf("defaulted fragment=%v err=%v", first, err)
	}
	first["mode"] = "changed"
	second, err := v.DefaultedObjectFragment("example", "#/$defs/claim", raw, limits)
	if err != nil || second["mode"] != "safe" {
		t.Fatal("fragment default aliases an earlier result")
	}
	for _, test := range []struct {
		pointer, stringValue string
		maxBytes             int
	}{
		{"#/$defs/missing", `{"id":"a"}`, 256},
		{"#/$defs/claim", `{"id":1}`, 256},
		{"#/$defs/claim", `{"id":"a"}`, len(raw)},
	} {
		if _, err := v.DefaultedObjectFragment("example", test.pointer, []byte(test.stringValue), ingress.Limits{MaxBytes: test.maxBytes, MaxDepth: 8}); err == nil {
			t.Error("accepted invalid or unbounded fragment")
		}
	}
}

func TestObjectFragmentUsesPublishedCompiledSchema(t *testing.T) {
	source := sourceFixture()
	source["schemas/example.json"] = &fstest.MapFile{Data: []byte(`{"type":"object","properties":{"claim":{"$ref":"#/$defs/claim"}},"$defs":{"claim":{"type":"object","additionalProperties":false,"required":["id"],"properties":{"id":{"type":"string"}}}}}`)}
	v, err := load(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 100, MaxDepth: 8}
	claim, err := v.DecodeObjectFragment("example", "#/$defs/claim", []byte(`{"id":"a"}`), limits)
	if err != nil {
		t.Fatal(err)
	}
	if claim["id"] != "a" {
		t.Errorf("fragment = %v, want id=a", claim)
	}
	for _, test := range []struct{ pointer, raw string }{
		{"#/$defs/claim", `{"id":1}`}, {"#/$defs/claim", `[]`}, {"#/$defs/claim", `{"id":"a","extra":true}`},
		{"#/$defs/claim", `{"id":"a","id":"b"}`}, {"#/$defs/missing", `{}`}, {"https://example.org/schema", `{}`},
	} {
		if _, err := v.DecodeObjectFragment("example", test.pointer, []byte(test.raw), limits); err == nil {
			t.Errorf("DecodeObjectFragment(%s,%s) accepted invalid input", test.pointer, test.raw)
		}
	}
}

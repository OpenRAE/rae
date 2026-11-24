package validation

import (
	"errors"
	"fmt"
	"testing"
	"testing/fstest"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// This uses the published graph from the CI timeout, rather than a small fixture.
func BenchmarkDecodePublishedObjectFragment(b *testing.B) {
	v, err := New(nil)
	if err != nil {
		b.Fatal(err)
	}
	raw := []byte(`{}`)
	limits := ingress.Limits{MaxBytes: 256, MaxDepth: 8}
	// Exclude the one-time compiled index from repeated-request measurements.
	if _, err := v.DecodeObjectFragment("instantiated-scenario-v1", "#/$defs/RealizationDesignationRecord", raw, limits); err == nil {
		b.Fatal("incomplete published record was accepted")
	}
	b.ReportAllocs()
	b.ResetTimer()
	for b.Loop() {
		_, err := v.DecodeObjectFragment("instantiated-scenario-v1", "#/$defs/RealizationDesignationRecord", raw, limits)
		classified, ok := errors.AsType[*fault.Error](err)
		if !ok || classified.Code() != codeContractSchemaMismatch {
			b.Fatalf("published fragment did not reject the incomplete record: %v", err)
		}
	}
}

func TestFragmentRequestsKeepSchemaRulesAndValuesIndependent(t *testing.T) {
	for _, id := range []string{"left", "right"} {
		fixture := sourceFixture()
		fixture["schemas/example.json"] = &fstest.MapFile{Data: fmt.Appendf(nil, `{"type":"object","properties":{"claim":{"$ref":"#/$defs/claim"}},"$defs":{"claim":{"type":"object","additionalProperties":false,"required":["id"],"properties":{"id":{"const":%q},"mode":{"type":"string","default":"safe"},"next":{"$ref":"#/$defs/claim"}},"x-raes-invariants":[{"id":"agreement","inputs":[{"contract_id":"example","instance_path":"#"}]}]},"unreachable":{"type":"object"}}}`, id)}
		base, err := load(fixture, nil)
		if err != nil {
			t.Fatal(err)
		}
		for _, refused := range []bool{false, true} {
			owner := fragmentRuleOwner(t, base, refused)
			for request := range 4 {
				t.Run(fmt.Sprintf("%s/refused-%t/request-%d", id, refused, request), func(t *testing.T) {
					t.Parallel()
					checkIndependentFragmentRequest(t, owner, id, refused)
				})
			}
		}
	}
}

func fragmentRuleOwner(t *testing.T, base *Validator, refused bool) *Validator {
	t.Helper()
	owner, err := base.WithRules([]Rule{{Key: Key{"example", "agreement"}, Check: func(Invocation) error {
		if refused {
			return errors.New("local rule refused")
		}
		return nil
	}}})
	if err != nil {
		t.Fatal(err)
	}
	return owner
}

func checkIndependentFragmentRequest(t *testing.T, owner *Validator, id string, refused bool) {
	t.Helper()
	const pointer = "#/$defs/claim"
	raw := fmt.Appendf(nil, `{"id":%q,"next":{"id":%q}}`, id, id)
	limits := ingress.Limits{MaxBytes: 256, MaxDepth: 8}
	first, err := owner.DefaultedObjectFragment("example", pointer, raw, limits)
	if err != nil || first["id"] != id || first["mode"] != "safe" {
		t.Fatalf("fragment used another schema or value: %v, %v", first, err)
	}
	first["mode"] = "changed"
	second, err := owner.DefaultedObjectFragment("example", pointer, raw, limits)
	if err != nil || second["mode"] != "safe" {
		t.Fatal("fragment returned an earlier request's mutable value")
	}
	if err := owner.CheckLocalFragment("example", pointer, raw, limits, func(SchemaInstance) error { return nil }); (err != nil) != refused {
		t.Fatalf("fragment reused another registry's rule result: %v", err)
	}
	for _, pointer := range []string{"#/$defs/unreachable", "#/$defs/unknown"} {
		_, err := owner.DecodeObjectFragment("example", pointer, []byte(`{}`), limits)
		classified, ok := errors.AsType[*fault.Error](err)
		if !ok || classified.Code() != codeContractFragmentUnknown {
			t.Fatalf("unreachable fragment became authority: %v", err)
		}
	}
	if _, err := owner.DecodeObjectFragment("example", pointer, []byte(`{"id":"other"}`), limits); err == nil {
		t.Fatal("an earlier valid request bypassed fresh validation")
	}
}

func TestFragmentLookupRefusesIncompleteSchemaGraph(t *testing.T) {
	root := &jsonschema.Schema{Location: "urn:example"}
	// Repeated edges consume work even when a node has already been visited.
	root.AllOf = make([]*jsonschema.Schema, 100001)
	child := &jsonschema.Schema{Location: "urn:example#/$defs/claim"}
	for i := range root.AllOf {
		root.AllOf[i] = child
	}
	owner := &Validator{contracts: map[string]contract{"example": {
		schema: root, fragments: func() map[string]*jsonschema.Schema { return indexSchemaFragments(root) },
	}}}
	_, err := owner.DecodeObjectFragment("example", "#", []byte(`{}`), ingress.Limits{MaxBytes: 256, MaxDepth: 8})
	classified, ok := errors.AsType[*fault.Error](err)
	if !ok || classified.Code() != codeContractFragmentUnknown {
		t.Fatalf("incomplete graph admitted a partially indexed fragment: %v", err)
	}
}

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

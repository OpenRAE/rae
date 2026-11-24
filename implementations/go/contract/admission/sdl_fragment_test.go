package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestSDLModelFragmentBoundary(t *testing.T) {
	validator, err := New()
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 1024, MaxDepth: 16}
	cases := []struct {
		name, contract, pointer, source string
		valid                           bool
	}{
		{"source", "sdl-authoring-input-v1", "#/$defs/Source", `{"name":"base"}`, true},
		{"required-field", "sdl-authoring-input-v1", "#/$defs/Source", `{}`, false},
		{"duplicate", "sdl-authoring-input-v1", "#/$defs/Source", `{"name":"a","name":"b"}`, false},
		{"array", "sdl-authoring-input-v1", "#/$defs/Source", `[]`, false},
		{"unknown-model", "sdl-authoring-input-v1", "#/$defs/Missing", `{}`, false},
		{"unknown-contract", "missing", "#/$defs/Source", `{}`, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := validator.CheckModelFragment(c.contract, c.pointer, []byte(c.source), limits)
			if (err == nil) != c.valid {
				t.Fatalf("valid=%v, want %v: %v", err == nil, c.valid, err)
			}
			if err != nil {
				if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
					t.Errorf("unclassified refusal: %v", err)
				}
			}
		})
	}
}

func TestSharedSchemasReplaceCallerRules(t *testing.T) {
	if _, err := NewWithSchemas(nil); err == nil {
		t.Fatal("accepted nil schemas")
	}
	if _, err := NewWithSchemas(new(validation.Validator)); err == nil {
		t.Fatal("accepted uninitialized schemas")
	}
	base, err := validation.New(nil)
	if err != nil {
		t.Fatal(err)
	}
	calls := 0
	rules := make([]validation.Rule, 0, len(base.Keys()))
	for _, key := range base.Keys() {
		rules = append(rules, validation.Rule{Key: key, Check: func(validation.Invocation) error {
			calls++
			return fault.New(fault.Operational, "caller-rule-invoked", nil)
		}})
	}
	supplied, err := base.WithRules(rules)
	if err != nil {
		t.Fatal(err)
	}
	owner, err := NewWithSchemas(supplied)
	if err != nil {
		t.Fatal(err)
	}
	if err = owner.CheckPortable("sdl-authoring-input-v1", []byte(`{"name":"a"}`), ingress.Limits{MaxBytes: 1024, MaxDepth: 16}); err != nil {
		t.Fatal(err)
	}
	if calls != 0 {
		t.Fatalf("owner invoked %d caller rule callbacks", calls)
	}
}

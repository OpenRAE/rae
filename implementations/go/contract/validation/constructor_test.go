package validation

import (
	"errors"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestNewKeepsRuleBindingsIndependent(t *testing.T) {
	base, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	rules := make([]Rule, 0, len(base.Keys()))
	for _, key := range base.Keys() {
		rules = append(rules, Rule{Key: key, Check: func(Invocation) error { return nil }})
	}
	first, err := New(rules)
	if err != nil {
		t.Fatal(err)
	}
	for i := range rules {
		rules[i].Check = func(Invocation) error { return errors.New("private callback failure") }
	}
	second, err := New(rules)
	if err != nil {
		t.Fatal(err)
	}
	data := []byte(`{"name":"example"}`)
	limits := ingress.Limits{MaxBytes: len(data)}
	if first.CheckLocal("sdl-authoring-input-v1", data, limits) != nil {
		t.Fatal("another constructor or the caller changed the first rule binding")
	}
	if second.CheckLocal("sdl-authoring-input-v1", data, limits) == nil {
		t.Fatal("another constructor replaced the second rule binding")
	}
	if base.CheckLocal("sdl-authoring-input-v1", data, limits) == nil {
		t.Fatal("construction populated another validator's missing rules")
	}
}

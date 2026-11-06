package validation

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestBindPublishedKeysAndLocalMode(t *testing.T) {
	base, err := load(sourceFixture(), nil)
	if err != nil {
		t.Fatal(err)
	}
	keys := base.Keys()
	if len(keys) != 1 || keys[0] != (Key{"example", "agreement"}) {
		t.Fatalf("Keys() = %v, want example/agreement", keys)
	}
	key := keys[0]
	keys[0] = Key{}
	calls := 0
	bound, err := base.WithRules([]Rule{{Key: key, Contextual: true, Check: func(Invocation) error { calls++; return nil }}})
	if err != nil {
		t.Fatal(err)
	}
	if err := bound.CheckLocal("example", []byte(`{}`), ingress.Limits{MaxBytes: 100, MaxDepth: 8}); err != nil {
		t.Fatal(err)
	}
	if calls != 0 {
		t.Errorf("local calls = %d, want 0", calls)
	}
	if err := bound.semantic("example", map[string]any{}, nil); err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Errorf("full calls = %d, want 1", calls)
	}
	if len(base.rules) != 0 {
		t.Error("WithRules mutated the original registry")
	}
	if _, err := bound.WithRules([]Rule{{Key: key, Check: nil}}); err == nil {
		t.Error("WithRules(nil callback) = nil, want refusal")
	}
}

func TestTypedNilContextFailsBeforeCallingRule(t *testing.T) {
	called := false
	v, err := load(sourceFixture(), []Rule{{Key: Key{"example", "agreement"}, RequiresContext: true, Check: func(Invocation) error { called = true; return nil }}})
	if err != nil {
		t.Fatal(err)
	}
	var absent *int
	if err := v.semantic("example", map[string]any{}, absent); err == nil {
		t.Error("typed nil context was admitted")
	}
	if called {
		t.Error("rule was called with typed nil authority")
	}
}

func TestSemanticSourceRetainsOriginalMemberOrder(t *testing.T) {
	var source string
	v, err := load(sourceFixture(), []Rule{{Key: Key{"example", "agreement"}, Check: func(i Invocation) error { source = i.Source; return nil }}})
	if err != nil {
		t.Fatal(err)
	}
	input := []byte(" {\"z\":1, \"a\":2} ")
	if err = v.CheckLocal("example", input, ingress.Limits{MaxBytes: 100, MaxDepth: 8}); err != nil {
		t.Fatal(err)
	}
	input[3] = 'x'
	if source != " {\"z\":1, \"a\":2} " {
		t.Fatalf("original source changed: %q", source)
	}
}

package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestRealizationEnvelopeCanonicalSemantics(t *testing.T) {
	e := boundTestOwner(t)
	v := fixtureObject(t, "fixtures/realization-envelope/realization-envelope-v1/valid/generic.json")
	rule, ok := e.checker("realization-envelope-canonical-semantics-valid")
	if !ok {
		t.Fatal("missing envelope rule")
	}
	if err := rule.check(validation.Invocation{Instance: v}); err != nil {
		t.Fatal(err)
	}
	object(v["configuration"])["configuration_digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	if err := rule.check(validation.Invocation{Instance: v}); err == nil {
		t.Error("accepted changed configuration digest")
	}
	for _, raw := range []string{
		`{"domains":{"a":{"kind":"record","fields":{"next":"a"}}}}`,
		`{"domains":{"a":{"kind":"enum","values":["one","two"]}},"bindings":[{"path":"nodes.host","scope":"node","posture":"exact","domain":"a"}]}`,
		`{"domains":{"a":{"kind":"exact","value":"one"}},"witness_policy":{"selections":{"a":"two"}}}`,
	} {
		if err := envelopeExpression(decodeRuleObject(t, raw)); err == nil {
			t.Error("accepted invalid envelope expression")
		}
	}
}

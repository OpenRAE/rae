package experiment

import (
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type forgedObligation struct {
	admission.Fragment

	called *bool
}

func (f forgedObligation) Document() any {
	*f.called = true
	return map[string]any{"obligation_id": "reset", "status": termSucceeded}
}
func TestRuntimeRetryRejectsForeignObligationWithoutCallingIt(t *testing.T) {
	owner, err := experimentOwner()
	if err != nil {
		t.Fatal(err)
	}
	native, err := admission.AdmitFragment(owner, admission.CleanupObligationResult, map[string]any{"obligation_id": "reset", "status": termSucceeded, "evidence_refs": []any{"evidence:clean"}, "residual_state_refs": []any{}}, runtimeIngress())
	if err != nil {
		t.Fatal(err)
	}
	called := false
	_, err = observationDocument(Observation{Kind: termRetry, ObligationResults: map[string]admission.Fragment{"reset": forgedObligation{Fragment: native, called: &called}}})
	if err == nil || called {
		t.Fatal("foreign obligation supplied projection behavior", err, called)
	}
}
func TestRuntimeHandoffsKeepSharedPortableValueBudgets(t *testing.T) {
	for _, test := range []struct {
		name  string
		value any
		valid bool
	}{
		{"scalar-at-limit", map[string]any{"value": strings.Repeat("a", 1<<20)}, true},
		{"scalar-over-limit", map[string]any{"value": strings.Repeat("a", (1<<20)+1)}, false},
		{"members-over-limit", make([]any, 16385), false},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := checkRuntimeValue(test.value); (err == nil) != test.valid {
				t.Fatal("runtime value bound changed", err)
			}
		})
	}
}

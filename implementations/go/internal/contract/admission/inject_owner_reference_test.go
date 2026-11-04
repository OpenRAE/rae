package admission

import (
	"encoding/json"
	"fmt"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type injectOwnerReference struct {
	Kind      string
	Documents []string
	Actor     string
	Admitted  bool
}

func TestInjectOwnerRetriesClaimsAndReadbacksMatchIndependentPython(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	var reference struct {
		Documents map[string]json.RawMessage
		Cases     []injectOwnerReference
	}
	readFullReferenceJSON(t, "testdata/inject-owner-verdicts.json", &reference)
	if len(reference.Cases) == 0 || len(reference.Documents) == 0 {
		t.Fatal("missing independent inject owner records")
	}
	for index, c := range reference.Cases {
		t.Run(fmt.Sprintf("%02d/%s", index, c.Kind), func(t *testing.T) {
			documents := make([]json.RawMessage, len(c.Documents))
			for index, key := range c.Documents {
				documents[index] = reference.Documents[key]
				if len(documents[index]) == 0 {
					t.Fatal("missing native inject document")
				}
			}
			err := checkInjectOwnerReference(t, e, c, documents)
			if (err == nil) != c.Admitted {
				t.Fatalf("inject owner differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

func checkInjectOwnerReference(t *testing.T, e *Validator, c injectOwnerReference, documents []json.RawMessage) error {
	t.Helper()
	context := testInjectContext{actor: c.Actor}
	if len(documents) > 0 {
		context.occurrence = documents[0]
	}
	if len(documents) > 1 {
		context.request = documents[1]
	}
	if len(documents) > 2 {
		context.outcome = documents[2]
	}
	invocation := validation.Invocation{Context: context}
	switch c.Kind {
	case "retry":
		invocation.Instance = decodeRuleObject(t, string(documents[1]))
		return e.injectRetry(invocation)
	case "claims":
		context.claims = flowRawList(documents)
		invocation.Context = context
		if len(documents) > 0 {
			invocation.Instance = decodeRuleObject(t, string(documents[0]))
		}
		return e.injectClaims(invocation)
	case "invocation":
		return injectInvocation(decodeRuleObject(t, string(documents[0])), decodeRuleObject(t, string(documents[1])))
	case "outcome":
		invocation.Instance = decodeRuleObject(t, string(documents[2]))
		return e.injectOutcome(invocation)
	case "computed-correlation", "correlation":
		if len(documents) > 3 {
			invocation.Instance = decodeRuleObject(t, string(documents[3]))
		}
		return e.injectCorrelation(invocation)
	default:
		t.Fatal("unknown native inject predicate")
		return invalid()
	}
}

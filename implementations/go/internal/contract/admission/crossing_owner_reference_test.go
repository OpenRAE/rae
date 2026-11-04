package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type crossingReferenceOwner struct {
	crossingTestContext

	evidence, authority []string
}

func (c crossingReferenceOwner) CrossingEvidenceRefs() []string  { return c.evidence }
func (c crossingReferenceOwner) CrossingAuthorityRefs() []string { return c.authority }
func TestCrossingOwnerInventoriesMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Name     string
			Admitted bool
			Context  struct {
				Records, Subjects, Policies []json.RawMessage
				Evidence, Authority         []string
			}
		}
	}
	readFullReferenceJSON(t, "testdata/crossing-owner-verdicts.json", &reference)
	if len(reference.Cases) != 36 {
		t.Fatal("crossing owner inventory changed", len(reference.Cases))
	}
	e := boundTestOwner(t)
	for _, c := range reference.Cases {
		t.Run(c.Name, func(t *testing.T) {
			s := c.Context
			owner := crossingReferenceOwner{crossingTestContext{records: flowRawList(s.Records), subjects: flowRawList(s.Subjects), policies: flowRawList(s.Policies)}, s.Evidence, s.Authority}
			err := e.crossingContext(validation.Invocation{Instance: decodeRuleObject(t, string(s.Records[0])), Context: owner})
			if (err == nil) != c.Admitted {
				t.Fatalf("crossing owner differs from native history (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

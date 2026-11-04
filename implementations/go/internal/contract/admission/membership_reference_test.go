package admission

import (
	"encoding/json"
	"fmt"
	"testing"
)

func TestPortableNodeMembershipSubsetMatchesIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Kind                   string
			Rule, Actual, Fallback json.RawMessage
			Admitted               bool
		}
	}
	readFullReferenceJSON(t, "testdata/membership-verdicts.json", &reference)
	if len(reference.Cases) != 324 {
		t.Fatal("independent portable-node membership inventory changed", len(reference.Cases))
	}
	for index, c := range reference.Cases {
		t.Run(fmt.Sprintf("%03d/%s", index, c.Kind), func(t *testing.T) {
			rule, actual, fallback := decodeRuleObject(t, string(c.Rule)), decodeRuleObject(t, string(c.Actual)), decodeRuleObject(t, string(c.Fallback))
			var err error
			if c.Kind == "record" {
				err = materializationMembershipRecord(rule, actual, fallback)
			} else {
				members := map[string]any{}
				for _, member := range array(actual) {
					members[stringAt(member, "address")] = member
				}
				err = materializationMembershipCollection(rule, members, fallback)
			}
			if (err == nil) != c.Admitted {
				t.Fatalf("portable-node membership differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

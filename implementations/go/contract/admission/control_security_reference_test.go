package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestControlSecurityFactsMatchIndependentPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []struct {
			Kind      string          `json:"kind"`
			Name      string          `json:"name"`
			Fact      json.RawMessage `json:"fact"`
			Cut       json.RawMessage `json:"cut"`
			Available bool            `json:"relation_available"`
			Admitted  bool            `json:"admitted"`
		} `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/control-security-verdicts.json", &reference)
	if len(reference.Cases) != 32 {
		t.Fatal("independent control security inventory changed")
	}
	e := boundTestOwner(t)
	incumbents := map[string]map[string]validation.Value{"legacy": admittedSecurityRelation(t, e, false), "owner": admittedSecurityRelation(t, e, true)}
	for _, c := range reference.Cases {
		t.Run(c.Kind+"/"+c.Name, func(t *testing.T) {
			relations := incumbents[c.Kind]
			if !c.Available {
				relations = nil
			}
			resolution := controlResolution{owner: e, snapshot: ControlResolutionSnapshot{FlowRelations: relations}}
			err := resolution.securityFact(decodeRuleObject(t, string(c.Fact)), decodeRuleObject(t, string(c.Cut)))
			if (err == nil) != c.Admitted {
				t.Fatalf("control security fact differs from Python (admitted=%v): %v", c.Admitted, err)
			}
		})
	}
}

func admittedSecurityRelation(t *testing.T, e *Validator, owner bool) map[string]validation.Value {
	t.Helper()
	raw, context := flowContextFixture(t, e)
	if owner {
		var fixture flowReferenceFixture
		readFullReferenceJSON(t, "testdata/flow-owner-resolution.json", &fixture)
		raw = fixture.Relation
		context.snapshot.Profile, context.snapshot.SourceLabels = fixture.Profile, flowRawMap(fixture.Sources)
		context.snapshot.OwnerReleaseAuthorities = fixture.OwnerReleaseAuthorities
		context.snapshot.OwnerSinks = map[FlowSink]FlowOwnerSink{context.snapshot.KnownSinks[0]: fixture.OwnerSink}
	}
	admitted, err := e.Validate(termParticipantFlowControlRelationV1, raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, context)
	if err != nil {
		t.Fatal(err)
	}
	relation := decodeRuleObject(t, string(raw))
	return map[string]validation.Value{stringAt(relation, "document_id"): admitted}
}

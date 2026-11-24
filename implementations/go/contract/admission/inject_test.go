package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestInjectLocalRules(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct{ id, rule string }{
		{"inject-trigger-request-v1", "inject-trigger-request-local-consistency"},
		{"inject-occurrence-v1", "inject-occurrence-local-consistency"},
		{"inject-occurrence-outcome-v1", "inject-occurrence-outcome-local-consistency"},
		{"inject-occurrence-correlation-v1", "inject-occurrence-correlation-local-consistency"},
	} {
		v := fixtureObject(t, "fixtures/control-plane/"+test.id+"/valid/participant-free-environment.json")
		rule, ok := e.checker(test.rule)
		if !ok {
			t.Error("missing rule", test.rule)
			continue
		}
		if err := rule.check(validation.Invocation{Instance: v}); err != nil {
			t.Errorf("%s: %v", test.id, err)
		}
	}
	v := fixtureObject(t, "fixtures/control-plane/inject-trigger-request-v1/valid/scheduled-fan-out.json")
	object(array(v["bindings"])[0])["binding"] = "orchestration.inject-binding.wrong.inject"
	rule, ok := e.checker("inject-trigger-request-local-consistency")
	if ok && rule.check(validation.Invocation{Instance: v}) == nil {
		t.Error("accepted foreign node binding")
	}
}

type testInjectContext struct {
	occurrence, request, outcome []byte
	claims                       [][]byte
	actor                        string
}

func (c testInjectContext) InjectOccurrence() []byte { return c.occurrence }
func (c testInjectContext) OperationRequest() []byte { return c.request }
func (c testInjectContext) InjectOutcome() []byte    { return c.outcome }
func (c testInjectContext) InjectClaims() [][]byte   { return c.claims }
func (c testInjectContext) ActorID() string          { return c.actor }

func TestInjectExactRetryAndClaimSet(t *testing.T) {
	e := boundTestOwner(t)
	occurrence := fixtureObject(t, "fixtures/control-plane/inject-occurrence-v1/valid/scheduled-fan-out.json")
	raw, err := json.Marshal(occurrence)
	if err != nil {
		t.Fatal(err)
	}
	c := testInjectContext{occurrence: raw, actor: stringAt(occurrence, "admission", "actor_id")}
	if err := validateTestDocument(t, e, "inject-trigger-request-v1", at(occurrence, "request"), c); err != nil {
		t.Fatal(err)
	}
	object(occurrence["request"])["expected_head"] = "changed"
	if err := validateTestDocument(t, e, "inject-trigger-request-v1", at(occurrence, "request"), c); err == nil {
		t.Error("accepted changed retry")
	}
	c.claims = [][]byte{raw, raw}
	if err := e.injectClaims(validation.Invocation{Instance: occurrence, Context: c}); err == nil {
		t.Error("accepted duplicate claims")
	}
}

func TestInjectOutcomeAndCorrelationSources(t *testing.T) {
	e := boundTestOwner(t)
	occurrence := fixtureObject(t, "fixtures/control-plane/inject-occurrence-v1/valid/participant-free-environment.json")
	request := fixtureObject(t, "fixtures/control-plane/backend-operation-request-v1/valid/inject-release.json")
	outcome := fixtureObject(t, "fixtures/control-plane/inject-occurrence-outcome-v1/valid/participant-free-environment.json")
	correlation := fixtureObject(t, "fixtures/control-plane/inject-occurrence-correlation-v1/valid/participant-free-environment.json")
	c := testInjectContext{}
	var err error
	c.occurrence, err = json.Marshal(occurrence)
	if err != nil {
		t.Fatal(err)
	}
	c.request, err = json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	c.outcome, err = json.Marshal(outcome)
	if err != nil {
		t.Fatal(err)
	}
	if err := validateTestDocument(t, e, "inject-occurrence-outcome-v1", outcome, c); err != nil {
		t.Fatal(err)
	}
	if err := validateTestDocument(t, e, "inject-occurrence-correlation-v1", correlation, c); err != nil {
		t.Fatal(err)
	}
	object(correlation["result"])["artifact_id"] = "foreign-result"
	if err := validateTestDocument(t, e, "inject-occurrence-correlation-v1", correlation, c); err == nil {
		t.Error("accepted foreign produced result")
	}
	object(array(outcome["bindings"])[0])["binding"] = map[string]any{"binding": "orchestration.inject-binding.other.release", "node": "provision.node.other", "instance": "other", "revision": "other"}
	if err := validateTestDocument(t, e, "inject-occurrence-outcome-v1", outcome, c); err == nil {
		t.Error("accepted foreign selected binding")
	}
}

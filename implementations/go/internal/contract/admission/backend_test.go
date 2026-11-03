package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestBackendOperationLocalRules(t *testing.T) {
	e := boundTestOwner(t)
	rule, ok := e.checker("backend-operation-local-consistency")
	if !ok {
		t.Fatal("missing backend rule")
	}
	for _, test := range []struct{ id, name string }{
		{"backend-operation-request-v1", "accepted"}, {"backend-operation-capabilities-v1", "provider"}, {"backend-operation-control-v1", "partial-cancel-01"},
		{"backend-operation-response-v1", "accepted-01"}, {"backend-operation-response-v1", "accepted-04"}, {"backend-operation-response-v1", "uncertain-03"},
	} {
		root := fixtureObject(t, "fixtures/control-plane/"+test.id+"/valid/"+test.name+".json")
		if err := rule.check(validation.Invocation{Key: validation.Key{ContractID: test.id}, Instance: root}); err != nil {
			t.Errorf("%s/%s: %v", test.id, test.name, err)
		}
	}
	request := fixtureObject(t, "fixtures/control-plane/backend-operation-request-v1/valid/accepted.json")
	object(request["budget"])["remaining_ms"] = json.Number("1001")
	if err := rule.check(validation.Invocation{Key: validation.Key{ContractID: "backend-operation-request-v1"}, Instance: request}); err == nil {
		t.Error("budget exceeded its original bound")
	}
	response := fixtureObject(t, "fixtures/control-plane/backend-operation-response-v1/valid/accepted-04.json")
	object(at(response, "message", "effects"))["cessation_established"] = false
	if err := rule.check(validation.Invocation{Key: validation.Key{ContractID: "backend-operation-response-v1"}, Instance: response}); err == nil {
		t.Error("success accepted unproved cessation")
	}
}

type testBackendContext struct{ request, control, admission, installed []byte }

func (c testBackendContext) OperationRequest() []byte      { return c.request }
func (c testBackendContext) OperationControl() []byte      { return c.control }
func (c testBackendContext) AdmissionResponse() []byte     { return c.admission }
func (c testBackendContext) InstalledCapabilities() []byte { return c.installed }

func TestBackendOperationTrustedJoins(t *testing.T) {
	e := boundTestOwner(t)
	request := fixtureObject(t, "fixtures/control-plane/backend-operation-request-v1/valid/accepted.json")
	capabilities := fixtureObject(t, "fixtures/control-plane/backend-operation-capabilities-v1/valid/provider.json")
	admission := fixtureObject(t, "fixtures/control-plane/backend-operation-response-v1/valid/accepted-01.json")
	context := testBackendContext{}
	var err error
	context.request, err = json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	context.installed, err = json.Marshal(capabilities)
	if err != nil {
		t.Fatal(err)
	}
	context.admission, err = json.Marshal(admission)
	if err != nil {
		t.Fatal(err)
	}
	if err := validateTestDocument(t, e, "backend-operation-capabilities-v1", capabilities, context); err != nil {
		t.Fatal(err)
	}
	if err := validateTestDocument(t, e, "backend-operation-response-v1", admission, context); err != nil {
		t.Fatal(err)
	}
	object(at(admission, "binding"))["attempt_id"] = "other-attempt"
	if err := validateTestDocument(t, e, "backend-operation-response-v1", admission, context); err == nil {
		t.Error("foreign attempt was accepted")
	}
	capabilities["backend_id"] = "uninstalled-provider"
	if err := validateTestDocument(t, e, "backend-operation-capabilities-v1", capabilities, context); err == nil {
		t.Error("uninstalled capability payload was accepted")
	}
}

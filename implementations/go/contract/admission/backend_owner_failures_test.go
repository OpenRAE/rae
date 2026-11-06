package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestBackendAdmissionRefusesCorruptIndependentOwners(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	owners := loadFullReferenceOwners(t).BackendOperation
	for _, field := range []string{"request", "admission", "installed"} {
		t.Run(field, func(t *testing.T) {
			c := testBackendContext{request: owners["request"], control: owners["control"], admission: owners["admission"], installed: owners["installed"]}
			switch field {
			case "request":
				c.request = []byte("{")
			case "admission":
				c.admission = []byte("{")
			case "installed":
				c.installed = []byte("{")
			}
			err := e.backendAdmission(validation.Invocation{Instance: decodeRuleObject(t, string(owners["installed"])), Context: c})
			if err == nil {
				t.Fatal("corrupt backend owner admitted")
			}
		})
	}
	for _, name := range []string{"cancel-race-02", "partial-cancel-02", "uncertain-03"} {
		t.Run(name, func(t *testing.T) {
			response := fixtureObject(t, "fixtures/control-plane/backend-operation-response-v1/valid/"+name+".json")
			c := testBackendContext{request: owners["request"], control: []byte("{")}
			if err := e.backendResponse(validation.Invocation{Instance: response, Context: c}); err == nil {
				t.Fatal("corrupt control owner admitted")
			}
		})
	}
}

package admission

import (
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type mixedBackendTestContext struct {
	*mixedTestContext
	testBackendContext

	profile  []byte
	bindings [][]byte
}

func (c *mixedBackendTestContext) MixedProfile() []byte    { return c.profile }
func (c *mixedBackendTestContext) MixedBindings() [][]byte { return c.bindings }

func mixedBackendFixture(t *testing.T, e *Validator, kind string) (any, *mixedBackendTestContext) {
	t.Helper()
	name, profile, service := "mixed-edge", "runtime-edge", "mixed-bridge"
	if kind == "handoff" {
		name, profile, service = "mixed-handoff", "staged", "mixed-transfer"
	}
	raw, composition := mixedContextFixture(t, e, profile)
	root := fixtureObject(t, "fixtures/control-plane/mixed-backend-execution-binding-v1/valid/"+name+".json")
	context := &mixedBackendTestContext{mixedTestContext: composition, profile: raw, bindings: [][]byte{controlJSON(t, root)}}
	context.request = controlJSON(t, fixtureObject(t, "fixtures/control-plane/backend-operation-request-v1/valid/"+name+".json"))
	context.installed = controlJSON(t, fixtureObject(t, "fixtures/control-plane/backend-operation-capabilities-v1/valid/"+service+".json"))
	if kind == "handoff" {
		var err error
		context.admission, err = os.ReadFile("testdata/mixed-handoff-admission.json")
		if err != nil {
			t.Fatal(err)
		}
	} else {
		context.admission = controlJSON(t, fixtureObject(t, "fixtures/control-plane/backend-operation-response-v1/valid/"+name+"-01.json"))
	}
	return root, context
}

func TestMixedBackendBindingsRequireExactProfileAndWillingness(t *testing.T) {
	e := boundTestOwner(t)
	for _, kind := range []string{"edge", "handoff"} {
		t.Run(kind, func(t *testing.T) {
			v, c := mixedBackendFixture(t, e, kind)
			i := validation.Invocation{Instance: v, Context: c}
			if err := e.mixedBackendBindings(i); err != nil {
				t.Fatal(err)
			}
			if err := e.mixedBackendAdmission(i); err != nil {
				t.Fatal(err)
			}
			if _, err := e.Validate("mixed-backend-execution-binding-v1", controlJSON(t, v), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, c); err != nil {
				t.Fatal(err)
			}
			mixedBackendMissingOwners(t, e, i, c)
		})
	}
}

func mixedBackendMissingOwners(t *testing.T, e *Validator, i validation.Invocation, c *mixedBackendTestContext) {
	t.Helper()
	c.bindings = append(c.bindings, c.bindings[0])
	if err := e.mixedBackendBindings(i); err == nil {
		t.Error("accepted duplicated installed binding")
	}
	c.bindings = nil
	if err := e.mixedBackendBindings(i); err == nil {
		t.Error("accepted missing installed binding")
	}
	c.admission = []byte(`{}`)
	if err := e.mixedBackendAdmission(i); err == nil {
		t.Error("accepted missing willingness")
	}
}

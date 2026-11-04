package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestMixedBackendAdaptersRefuseSubstitutedOwners(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	for _, name := range []string{"profile", "bindings", "binding-count", "request", "capabilities", "response", "command", "provider", "operation", "composition"} {
		t.Run(name, func(t *testing.T) {
			v, c := mixedBackendFixture(t, e, "edge")
			switch name {
			case "profile":
				c.profile = []byte("{")
			case "bindings":
				c.bindings = [][]byte{[]byte("{")}
			case "binding-count":
				c.bindings = make([][]byte, 2049)
			case "request":
				c.request = []byte("{")
			case "capabilities":
				c.installed = []byte("{")
			case "response":
				c.admission = []byte("{")
			case "command", "provider", "operation":
				request := decodeRuleObject(t, string(c.request))
				alterMixedBackendRequest(request, name)
				c.request = controlJSON(t, request)
			case "composition":
				c.snapshot.TimeModels = nil
			}
			i := validation.Invocation{Instance: v, Context: c}
			var err error
			switch name {
			case "profile", "bindings", "binding-count", "composition":
				err = e.mixedBackendBindings(i)
			default:
				err = e.mixedBackendAdmission(i)
			}
			if err == nil {
				t.Fatal("substituted mixed backend owner admitted")
			}
		})
	}
}
func alterMixedBackendRequest(v any, name string) {
	switch name {
	case "command":
		object(at(v, "command"))["artifact_id"] = "foreign"
	case "provider":
		object(at(v, "binding"))["backend_id"] = "foreign"
	case "operation":
		object(at(v, "binding", "context"))["operation_kind"] = "foreign"
	}
}

func TestMixedStageAdaptersRefuseCorruptTranscriptAndTimeOwners(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	for _, name := range []string{"binding", "request", "responses", "controls", "reports", "model", "before", "after", "composition", "ref", "digest"} {
		t.Run(name, func(t *testing.T) {
			c := mixedStageFixtureContext(t, e, "mixed-handoff")
			switch name {
			case "binding":
				c.binding = []byte("{")
			case "request":
				c.request = []byte("{")
			case "responses":
				c.responses = [][]byte{[]byte("{")}
			case "controls":
				c.controls = [][]byte{[]byte("{")}
			case "reports":
				c.reports = [][]byte{[]byte("{")}
			case "model":
				c.snapshot.TimeModel = validation.Value{}
			case "before":
				c.snapshot.TimeState = validation.Value{}
			case "after":
				c.snapshot.PostTimeState = c.snapshot.TimeModel
			case "composition":
				c.snapshot.CompositionState = []byte("{")
			case "ref":
				c.snapshot.TimeModelRef = "foreign"
			case "digest":
				c.snapshot.TimeModelDigest = "sha256:foreign"
			}
			if _, err := e.mixedStageInputs(c); err == nil {
				t.Fatal("corrupt mixed stage owner admitted")
			}
		})
	}
}

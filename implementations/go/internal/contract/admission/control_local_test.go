package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestControlAndCrossingKeepLifecycleStagesSeparate(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct{ id, rule, name string }{
		{"participant-control-occurrence-v1", "participant-control-occurrence-not-lifecycle-evidence", "proposal"},
		{"participant-crossing-occurrence-v1", "participant-crossing-stage-separation", "request"},
	} {
		v := fixtureObject(t, "fixtures/participant-runtime/"+test.id+"/valid/"+test.name+".json")
		rule, ok := e.checker(test.rule)
		if !ok {
			t.Fatal("missing rule", test.rule)
		}
		if err := rule.check(validation.Invocation{Instance: v}); err != nil {
			t.Fatal(err)
		}
		occurrence := object(v["occurrence"])
		occurrence["effective_order"] = json.Number("999999")
		if err := rule.check(validation.Invocation{Instance: v}); err == nil {
			t.Error("accepted occurrence outside its validity interval")
		}
	}
}
func TestParticipantControlSelectionGraph(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct{ version, name string }{{"v1", "teaching-inject"}, {"v2", "disjoint-sinks"}, {"v2", "owner-flow"}} {
		v := fixtureObject(t, "fixtures/participant-runtime/participant-control-selection-"+test.version+"/valid/"+test.name+".json")
		if err := e.controlSelection(validation.Invocation{Instance: v}); err != nil {
			t.Errorf("%s: %v", test.name, err)
		}
		object(array(v["slots"])[0])["instance_id"] = "foreign-provider"
		if err := e.controlSelection(validation.Invocation{Instance: v}); err == nil {
			t.Error("accepted slot from an unselected provider")
		}
	}
}

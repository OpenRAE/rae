package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestRuntimeFactBindingJoins(t *testing.T) {
	e := boundTestOwner(t)
	rule, ok := e.checker("runtime-fact-binding-references-resolve")
	if !ok {
		t.Fatal("missing fact binding rule")
	}
	for _, name := range []string{"observation-to-action", "secret-reference", "failure-dispositions", "cross-backend-portable"} {
		root := fixtureObject(t, "fixtures/participant-runtime/runtime-fact-binding-plane-v1/valid/"+name+".json")
		if err := rule.check(validation.Invocation{Instance: root}); err != nil {
			t.Errorf("fixture %s: %v", name, err)
		}
	}
	for _, test := range []struct {
		name   string
		mutate func(map[string]any)
	}{
		{"gap in versions", func(v map[string]any) { object(array(v["versions"])[0])["sequence"] = json.Number("2") }},
		{"undeclared version", func(v map[string]any) { object(array(v["versions"])[0])["fact_id"] = "missing" }},
		{"wrong sink target", func(v map[string]any) { object(array(v["events"])[0])["target_field"] = "input.other" }},
		{"missing authorization", func(v map[string]any) { object(array(v["events"])[0])["authorization_refs"] = []any{} }},
		{"unbound version", func(v map[string]any) { object(array(v["events"])[0])["fact_version_id"] = nil }},
		{"scope mismatch", func(v map[string]any) { object(array(v["events"])[0])["run_id"] = "other-run" }},
		{"projection value mismatch", func(v map[string]any) { object(array(v["projections"])[0])["value"] = "other-value" }},
	} {
		t.Run(test.name, func(t *testing.T) {
			root := fixtureObject(t, "fixtures/participant-runtime/runtime-fact-binding-plane-v1/valid/observation-to-action.json")
			test.mutate(root)
			if err := rule.check(validation.Invocation{Instance: root}); err == nil {
				t.Error("contradictory fact binding accepted")
			}
		})
	}
}

func TestRuntimeFactReferenceComparisonBoundary(t *testing.T) {
	e := boundTestOwner(t)
	root := fixtureObject(t, "fixtures/participant-runtime/runtime-fact-binding-plane-v1/valid/observation-to-action.json")
	for _, field := range []string{"declarations", "sinks", "versions", "projections"} {
		object(array(root[field])[0])["value_type"] = "number"
	}
	object(array(root["versions"])[0])["value"] = json.Number("1")
	object(array(root["projections"])[0])["value"] = true
	if err := e.factPlane(validation.Invocation{Instance: root}); err != nil {
		t.Errorf("reference model comparison was changed: %v", err)
	}
	object(array(root["versions"])[0])["value"] = true
	if err := e.factPlane(validation.Invocation{Instance: root}); err == nil {
		t.Error("Boolean concrete version was accepted as a number")
	}
}

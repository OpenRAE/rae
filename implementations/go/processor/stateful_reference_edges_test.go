package processor

import (
	"encoding/json"
	"slices"
	"testing"
)

func TestStatefulDependenciesRequireUniqueOrQualifiedNativeIdentity(t *testing.T) {
	for _, test := range []struct {
		ref, want string
	}{
		{"generated_artifacts.shared", "provision.generated-artifact.shared"},
		{"persistent_volumes.shared", "provision.persistent-volume.shared"},
		{"artifact", "provision.generated-artifact.artifact"},
		{"volume", "provision.persistent-volume.volume"},
		{"shared", ""}, {"unknown", ""}, {"generated_artifacts.unknown", ""},
	} {
		t.Run(test.ref, func(t *testing.T) {
			state := compilerState{}
			if err := json.Unmarshal([]byte(`{"generated_artifacts":{"shared":{},"artifact":{}},"persistent_volumes":{"shared":{},"volume":{}}}`), &state.input.model); err != nil {
				t.Fatal(err)
			}
			got := state.statefulDependency(test.ref)
			if got != test.want || (state.err != nil) != (test.want == "") {
				t.Fatalf("dependency=%q %v, want %q", got, state.err, test.want)
			}
		})
	}
}

func TestMixedScriptStepsKeepPositionAndExplicitTargetDependencies(t *testing.T) {
	state := compilerState{}
	source := mixedSource{ScriptSteps: []json.RawMessage{
		json.RawMessage(`{"step_id":"first","permitted_transition_ref":"advance","expected_state_revision":7}`),
		json.RawMessage(`{"step_id":"second","permitted_transition_ref":"rewind","target_step_ref":"first","target_kind":"script-step","valid_from_order":2,"valid_until_order":4}`),
	}}
	steps := state.compileMixedScript("control", source)
	if state.err != nil || len(steps) != 2 {
		t.Fatalf("script compilation: %+v %v", steps, state.err)
	}
	prefix := "participant.behavior-specification.control."
	if steps[0].Position != "1" || steps[0].TargetStepAddress != "" || steps[0].ExpectedStateRevision == nil || *steps[0].ExpectedStateRevision != "7" {
		t.Fatalf("first step lost revision or position: %+v", steps[0])
	}
	second := steps[1]
	if second.Position != "2" || second.TargetStepAddress != prefix+"script-step.first" || !slices.Equal(second.RefreshDependencies, []string{prefix + "permitted-transition.rewind", prefix + "script-step.first"}) {
		t.Fatalf("script target dependencies changed: %+v", second)
	}
	if second.ValidFromOrder == nil || *second.ValidFromOrder != "2" || second.ValidUntilOrder == nil || *second.ValidUntilOrder != "4" {
		t.Fatal("script validity window changed")
	}
	source.ScriptSteps = []json.RawMessage{json.RawMessage(`[]`)}
	if state.compileMixedScript("control", source) != nil || state.err == nil {
		t.Fatal("malformed script step produced native authority")
	}
}

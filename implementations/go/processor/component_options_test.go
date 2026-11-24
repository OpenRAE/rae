package processor

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestComponentOptionsFollowCompiledResourcesAndRejectErrorModels(t *testing.T) {
	model := &runtimeModel{view: CompiledScenario{Resources: []Resource{{Domain: termOrchestration}, {Domain: termEvaluation}}, ParticipantResources: []Resource{{Kind: termBehaviorSpecification}, {Kind: termParticipantBehavior}}, CaptureDemands: []CaptureDemand{{}}}}
	model.view.TimeModel.Clocks = []Clock{{}}
	options, err := CompiledComponentOptions(model)
	if err != nil || options != (ComponentOptions{WithOrchestrator: true, WithEvaluator: true, WithParticipantRuntime: true, WithTime: true, WithObservation: true}) {
		t.Fatalf("component needs lost: %+v %v", options, err)
	}
	model.view.Diagnostics = []diagnostic.Diagnostic{{Severity: "warning"}}
	if _, err := CompiledComponentOptions(model); err != nil {
		t.Fatal("warning became a compilation error")
	}
	model.view.Diagnostics = []diagnostic.Diagnostic{{Severity: "error"}}
	if _, err := CompiledComponentOptions(model); err == nil {
		t.Fatal("error model granted component authority")
	}
	if _, err := CompiledComponentOptions(nil); err == nil {
		t.Fatal("missing model granted component authority")
	}
}

func TestConcreteCompilationAndComponentFacadeKeepNativeScenario(t *testing.T) {
	scenario, err := sdl.Parse([]byte("name: native-options\n"), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	instance, err := sdl.Instantiate(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := CompileInstantiated(instance)
	if err != nil || compiled.Model().View().Name != "native-options" {
		t.Fatalf("concrete compilation failed: %v", err)
	}
	if _, err := ScenarioComponentOptions(scenario); err != nil {
		t.Fatal(err)
	}
	if _, err := ScenarioComponentOptions(nil); err == nil {
		t.Fatal("missing scenario accepted")
	}
	if _, err := CompileInstantiated(nil); err == nil {
		t.Fatal("missing concrete scenario accepted")
	}
}

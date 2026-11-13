package processor_test

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompileWorkflowAndObjectiveDependencies(t *testing.T) {
	scenario, err := sdl.Parse([]byte(`name: workflow
nodes:
  server: {type: compute}
entities:
  blue: {role: blue}
propositions:
  health:
    description: declared runtime
    subjects: [nodes.server]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  gate: {proposition: health, role: precondition}
  result: {proposition: health, role: postcondition}
objectives:
  first: {owner: blue, success: {assertions: [result]}}
workflows:
  flow:
    start: branch
    steps:
      branch: {type: decision, when: {assertions: [gate]}, then: execute, else: finish}
      execute: {type: objective, objective: first, on_success: finish}
      finish: {type: end}
`), sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	compiled, err := processor.Compile(scenario, nil)
	if err != nil {
		t.Fatal(err)
	}
	resources := map[string]processor.Resource{}
	for _, resource := range compiled.Model().View().Resources {
		resources[resource.Address] = resource
	}
	objective := resources["evaluation.objective.first"]
	if len(objective.OrderingDependencies) != 1 || objective.OrderingDependencies[0] != "evaluation.assertion.result" {
		t.Fatalf("objective dependencies = %v", objective.OrderingDependencies)
	}
	workflow := resources["orchestration.workflow.flow"]
	if len(workflow.OrderingDependencies) != 0 || len(workflow.RefreshDependencies) != 2 || !workflow.UsesAssertionRefs || len(workflow.RequiredFeatures) != 1 || workflow.RequiredFeatures[0] != "decision" {
		t.Fatalf("workflow facts = %#v", workflow)
	}
	var payload struct {
		ControlSteps map[string]struct {
			StepType      string `json:"step_type"`
			StateContract struct {
				StateObservable bool `json:"state_observable"`
			} `json:"state_contract"`
		} `json:"control_steps"`
	}
	if err := json.Unmarshal(workflow.Payload.JSON(), &payload); err != nil {
		t.Fatal(err)
	}
	if !payload.ControlSteps["execute"].StateContract.StateObservable || payload.ControlSteps["branch"].StateContract.StateObservable {
		t.Fatal("workflow state observability was flattened")
	}
}

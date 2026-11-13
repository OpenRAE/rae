package processor

import (
	"encoding/json"
	"slices"
	"testing"
)

func TestSharedServiceRelationshipKeepsTenantAndIndependentStateOwners(t *testing.T) {
	state := compilerState{}
	if err := json.Unmarshal([]byte(`{"relationships":{"shared":{"source":"deployment_tenants.consumer","shared_service":{"mutable_state_owner":"provider","reset_generation_owner":"operator"}}}}`), &state.input.model); err != nil {
		t.Fatal(err)
	}
	wire := serviceMaterializationWire{}
	state.materializationServiceRelationship("relationships.shared", &wire)
	if state.err != nil || wire.ConsumerTenantRef != "consumer" || wire.MutableStateOwner != "provider" || wire.ResetGenerationOwner != "operator" {
		t.Fatalf("shared service ownership changed: %+v %v", wire, state.err)
	}
	if err := json.Unmarshal([]byte(`{"relationships":{"shared":{"shared_service":[]}}}`), &state.input.model); err != nil {
		t.Fatal(err)
	}
	state.materializationServiceRelationship("shared", &wire)
	if state.err == nil {
		t.Fatal("invalid shared service record granted state ownership")
	}
}

func TestObjectiveWorkflowWindowsRefuseUnboundAndOutOfWindowSteps(t *testing.T) {
	state := compilerState{knownNames: map[string]map[string]bool{termWorkflows: {"inside": true, "outside": true}}}
	if err := json.Unmarshal([]byte(`{"workflows":{"inside":{"steps":{"run":{}}},"outside":{"steps":{"run":{}}}}}`), &state.input.model); err != nil {
		t.Fatal(err)
	}
	output := objectivePayload{}
	compiler := objectiveWindowCompiler{state: &state, owner: "evaluation.objective.result", output: &output, window: &objectiveWindow{Workflows: []string{"inside", "unknown"}, Steps: []string{"invalid", ".run", "inside.", "missing.run", "outside.run", "inside.missing", "inside.run", "inside.run"}}}
	workflows := compiler.workflows()
	compiler.steps(workflows)
	wantCodes := []string{"evaluation.workflow-ref-unbound", "evaluation.workflow-step-ref-invalid-format", "evaluation.workflow-step-ref-invalid-format", "evaluation.workflow-step-ref-invalid-format", "evaluation.workflow-step-ref-workflow-unbound", "evaluation.workflow-step-ref-workflow-outside-window", "evaluation.workflow-step-ref-step-unbound"}
	codes := make([]string, len(compiler.findings))
	for i, finding := range compiler.findings {
		codes[i] = finding.Code
	}
	if !slices.Equal(codes, wantCodes) || !slices.Equal(output.WindowStepRefs, []string{"inside.run"}) {
		t.Fatalf("window references escaped authority: %v %+v", codes, output)
	}
	compiler.window = &objectiveWindow{Steps: []string{"inside.run"}}
	compiler.findings = nil
	compiler.steps(nil)
	if len(compiler.findings) != 2 || compiler.findings[0].Code != "evaluation.workflow-step-ref-window-missing-workflow" {
		t.Fatalf("step without window workflow accepted: %+v", compiler.findings)
	}
}

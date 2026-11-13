package processor

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type objectiveSource struct {
	Owner               string `json:"owner"`
	AssignedParticipant string `json:"assigned_participant"`
	Success             struct {
		Assertions []string `json:"assertions"`
	} `json:"success"`
	DependsOn []string         `json:"depends_on"`
	Window    *objectiveWindow `json:"window"`
}
type objectiveWindow struct {
	Stories   []string `json:"stories"`
	Scripts   []string `json:"scripts"`
	Events    []string `json:"events"`
	Workflows []string `json:"workflows"`
	Steps     []string `json:"steps"`
}

type objectiveWindowReference struct {
	Raw             string   `json:"raw"`
	CanonicalName   string   `json:"canonical_name"`
	ReferenceKind   string   `json:"reference_kind"`
	DependencyRoles []string `json:"dependency_roles"`
	WorkflowName    string   `json:"workflow_name"`
	StepName        string   `json:"step_name"`
	NamespacePath   []string `json:"namespace_path"`
}
type objectivePayload struct {
	Name                        string                      `json:"name"`
	Spec                        json.RawMessage             `json:"spec"`
	OwnerName                   string                      `json:"owner_name"`
	AssignedParticipantName     string                      `json:"assigned_participant_name"`
	AssignedParticipantAddress  string                      `json:"assigned_participant_address"`
	SuccessAddresses            []string                    `json:"success_addresses"`
	ObjectiveDependencies       []string                    `json:"objective_dependencies"`
	WindowStoryAddresses        []string                    `json:"window_story_addresses"`
	WindowScriptAddresses       []string                    `json:"window_script_addresses"`
	WindowEventAddresses        []string                    `json:"window_event_addresses"`
	WindowWorkflowAddresses     []string                    `json:"window_workflow_addresses"`
	WindowStepRefs              []string                    `json:"window_step_refs"`
	WindowStepWorkflowAddresses []string                    `json:"window_step_workflow_addresses"`
	WindowReferences            []objectiveWindowReference  `json:"window_references"`
	ResultContract              evaluationResultContract    `json:"result_contract"`
	ExecutionContract           evaluationExecutionContract `json:"execution_contract"`
}

func (state *compilerState) compileObjectives() {
	objectives := fieldValue(state.input.model.Objectives)
	findings := []diagnostic.Diagnostic{}
	for _, name := range orderedNames(objectives, state.names(termObjectives)) {
		var source objectiveSource
		if err := json.Unmarshal(objectives[name], &source); err != nil {
			state.err = invalidCompiled()
			return
		}
		addr := state.address(termEvaluation, termObjective, name)
		successes, local := state.namedReferences(termAssertions, termEvaluation, termAssertion, source.Success.Assertions, addr, termEvaluation, "evaluation.assertion-ref", termAssertion)
		findings = append(findings, local...)
		dependencies, local := state.namedReferences(termObjectives, termEvaluation, termObjective, source.DependsOn, addr, termEvaluation, "evaluation.objective-ref", termObjective)
		findings = append(findings, local...)
		resultContract, executionContract := evaluationContracts(termObjective)
		payload := objectivePayload{Name: name, Spec: objectives[name], OwnerName: source.Owner, AssignedParticipantName: source.AssignedParticipant, SuccessAddresses: successes, ObjectiveDependencies: dependencies, WindowStoryAddresses: []string{}, WindowScriptAddresses: []string{}, WindowEventAddresses: []string{}, WindowWorkflowAddresses: []string{}, WindowStepRefs: []string{}, WindowStepWorkflowAddresses: []string{}, WindowReferences: []objectiveWindowReference{}, ResultContract: resultContract, ExecutionContract: executionContract}
		if source.AssignedParticipant != "" {
			payload.AssignedParticipantAddress = state.address(termParticipant, "behavior", source.AssignedParticipant)
		}
		if source.Window != nil {
			windowFindings := state.compileObjectiveWindow(&payload, source, addr)
			findings = append(findings, windowFindings...)
		}
		ordering := dedupe(append(append([]string{}, successes...), dependencies...))
		refresh := append([]string{}, ordering...)
		for _, addresses := range [][]string{payload.WindowStoryAddresses, payload.WindowScriptAddresses, payload.WindowEventAddresses, payload.WindowWorkflowAddresses, payload.WindowStepWorkflowAddresses} {
			refresh = append(refresh, addresses...)
		}
		state.model.Resources = append(state.model.Resources, Resource{Address: addr, Name: name, Domain: termEvaluation, Kind: termObjective, OrderingDependencies: ordering, RefreshDependencies: dedupe(refresh), Payload: state.payload(payload)})
	}
	state.addDiagnostics(findings)
}
func (state *compilerState) compileObjectiveWindow(output *objectivePayload, source objectiveSource, owner string) []diagnostic.Diagnostic {
	compiler := objectiveWindowCompiler{state: state, output: output, window: source.Window, owner: owner, findings: []diagnostic.Diagnostic{}}
	scripts := compiler.stories()
	scripts = compiler.scripts(scripts)
	compiler.events(scripts)
	workflows := compiler.workflows()
	compiler.steps(workflows)
	output.WindowStepWorkflowAddresses = dedupe(output.WindowStepWorkflowAddresses)
	return compiler.findings
}

type objectiveWindowCompiler struct {
	state    *compilerState
	output   *objectivePayload
	window   *objectiveWindow
	owner    string
	findings []diagnostic.Diagnostic
}

func (compiler *objectiveWindowCompiler) addReference(ref, kind, workflow, step string) {
	compiler.output.WindowReferences = append(compiler.output.WindowReferences, objectiveWindowReference{Raw: ref, CanonicalName: ref, ReferenceKind: kind, DependencyRoles: []string{"refresh"}, WorkflowName: workflow, StepName: step, NamespacePath: []string{}})
}
func (compiler *objectiveWindowCompiler) stories() map[string]bool {
	reachableScripts := map[string]bool{}
	stories := fieldValue(compiler.state.input.model.Stories)
	for _, ref := range dedupe(compiler.window.Stories) {
		if !compiler.state.known(termStories)[ref] {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.story-ref-unbound", termEvaluation, compiler.owner, "Reference '"+ref+"' does not resolve to a defined story."))
			continue
		}
		compiler.output.WindowStoryAddresses = append(compiler.output.WindowStoryAddresses, compiler.state.address(termOrchestration, termStory, ref))
		compiler.addReference(ref, termStory, "", "")
		for _, script := range fieldValue(stories[ref].Scripts) {
			reachableScripts[script] = true
		}
	}
	return reachableScripts
}
func (compiler *objectiveWindowCompiler) scripts(reachableScripts map[string]bool) map[string]bool {
	referencedScripts := []string{}
	for _, ref := range dedupe(compiler.window.Scripts) {
		if !compiler.state.known(termScripts)[ref] {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.script-ref-unbound", termEvaluation, compiler.owner, "Reference '"+ref+"' does not resolve to a defined script."))
			continue
		}
		if len(compiler.window.Stories) > 0 && !reachableScripts[ref] {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.script-ref-outside-window-stories", termEvaluation, compiler.owner, "Reference '"+ref+"' is not included by the objective window's referenced stories."))
		}
		compiler.output.WindowScriptAddresses = append(compiler.output.WindowScriptAddresses, compiler.state.address(termOrchestration, termScript, ref))
		compiler.addReference(ref, termScript, "", "")
		referencedScripts = append(referencedScripts, ref)
	}
	if len(referencedScripts) > 0 {
		reachableScripts = map[string]bool{}
		for _, ref := range referencedScripts {
			reachableScripts[ref] = true
		}
	}
	return reachableScripts
}
func (compiler *objectiveWindowCompiler) events(reachableScripts map[string]bool) {
	reachableEvents := map[string]bool{}
	scripts := fieldValue(compiler.state.input.model.Scripts)
	for script := range reachableScripts {
		for event := range fieldValue(scripts[script].Events) {
			reachableEvents[event] = true
		}
	}
	for _, ref := range dedupe(compiler.window.Events) {
		if !compiler.state.known(termEvents)[ref] {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.event-ref-unbound", termEvaluation, compiler.owner, "Reference '"+ref+"' does not resolve to a defined event."))
			continue
		}
		if (len(compiler.window.Scripts) > 0 || len(compiler.window.Stories) > 0) && !reachableEvents[ref] {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.event-ref-outside-window-scripts", termEvaluation, compiler.owner, "Reference '"+ref+"' is not included by the objective window's referenced scripts."))
		}
		compiler.output.WindowEventAddresses = append(compiler.output.WindowEventAddresses, compiler.state.address(termOrchestration, termEvent, ref))
		compiler.addReference(ref, termEvent, "", "")
	}
}
func (compiler *objectiveWindowCompiler) workflows() map[string]bool {
	referencedWorkflows := map[string]bool{}
	for _, ref := range dedupe(compiler.window.Workflows) {
		if !compiler.state.known(termWorkflows)[ref] {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.workflow-ref-unbound", termEvaluation, compiler.owner, "Reference '"+ref+"' does not resolve to a defined workflow."))
			continue
		}
		referencedWorkflows[ref] = true
		compiler.output.WindowWorkflowAddresses = append(compiler.output.WindowWorkflowAddresses, compiler.state.address(termOrchestration, termWorkflow, ref))
		compiler.addReference(ref, termWorkflow, ref, "")
	}
	return referencedWorkflows
}
func (compiler *objectiveWindowCompiler) steps(referencedWorkflows map[string]bool) {
	if len(compiler.window.Steps) > 0 && len(compiler.window.Workflows) == 0 {
		compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.workflow-step-ref-window-missing-workflow", termEvaluation, compiler.owner, "Workflow step references require at least one referenced workflow."))
	}
	workflows := fieldValue(compiler.state.input.model.Workflows)
	for _, ref := range dedupe(compiler.window.Steps) {
		split := strings.LastIndexByte(ref, '.')
		if split <= 0 || split == len(ref)-1 {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.workflow-step-ref-invalid-format", termEvaluation, compiler.owner, "Reference '"+ref+"' must use '<workflow>.<step>' syntax."))
			continue
		}
		workflow, step := ref[:split], ref[split+1:]
		if !compiler.state.known(termWorkflows)[workflow] {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.workflow-step-ref-workflow-unbound", termEvaluation, compiler.owner, "Reference '"+ref+"' does not resolve to a defined workflow."))
			continue
		}
		if !referencedWorkflows[workflow] {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.workflow-step-ref-workflow-outside-window", termEvaluation, compiler.owner, "Reference '"+ref+"' is not part of the objective window's referenced workflows."))
			continue
		}
		if _, exists := fieldValue(workflows[workflow].Steps)[step]; !exists {
			compiler.findings = append(compiler.findings, compileDiagnostic("evaluation.workflow-step-ref-step-unbound", termEvaluation, compiler.owner, "Reference '"+ref+"' does not resolve to a defined workflow step."))
			continue
		}
		compiler.output.WindowStepRefs = append(compiler.output.WindowStepRefs, ref)
		compiler.output.WindowStepWorkflowAddresses = append(compiler.output.WindowStepWorkflowAddresses, compiler.state.address(termOrchestration, termWorkflow, workflow))
		compiler.addReference(ref, "workflow_step", workflow, step)
	}
}

package processor

import (
	"encoding/json"
	"maps"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

const workflowStateVersion = "workflow-step-state/v1"

func workflowStateContract(kind string) workflowStepState {
	result := workflowStepState{StepType: kind, ObservableOutcomes: []string{}}
	switch kind {
	case termObjective, termParallel, termCall:
		one := 1
		result.FixedAttempts = &one
		result.ObservableOutcomes = []string{"succeeded", "failed"}
	case termRetry:
		result.ObservableOutcomes = []string{"succeeded", "exhausted"}
	}
	result.StateObservable = len(result.ObservableOutcomes) > 0
	result.SupportsAttemptCounts = result.StateObservable
	return result
}
func workflowEdges(step workflowStepSource) []string {
	result := []string{}
	switch step.Type {
	case termObjective, termCall:
		result = append(result, step.OnSuccess, step.OnFailure)
	case termDecision:
		result = append(result, step.Then, step.Else)
	case termSwitch:
		for _, item := range step.Cases {
			result = append(result, item.Next)
		}
		result = append(result, step.Default)
	case termParallel:
		result = append(result, step.Branches...)
		result = append(result, step.OnFailure)
	case "join":
		result = append(result, step.Next)
	case termRetry:
		result = append(result, step.OnSuccess, step.OnExhausted)
	}
	filtered := []string{}
	for _, edge := range result {
		if edge != "" {
			filtered = append(filtered, edge)
		}
	}
	return dedupe(filtered)
}
func (state *compilerState) compileWorkflowPredicate(source workflowPredicateSource, owner string, output *workflowCompilation) workflowPredicate {
	assertions, local := state.namedReferences(termAssertions, termEvaluation, termAssertion, source.Assertions, referenceFindingContext{owner: owner, domain: termOrchestration, code: "orchestration.assertion-ref", label: termAssertion})
	output.diagnostics = append(output.diagnostics, local...)
	objectives, local := state.namedReferences(termObjectives, termEvaluation, termObjective, source.Objectives, referenceFindingContext{owner: owner, domain: termOrchestration, code: "orchestration.objective-ref", label: termObjective})
	output.diagnostics = append(output.diagnostics, local...)
	result := workflowPredicate{AssertionAddresses: assertions, ObjectiveAddresses: objectives, StepStatePredicates: []workflowStatePredicate{}}
	for _, predicate := range source.Steps {
		if predicate.Step == "" {
			continue
		}
		result.StepStatePredicates = append(result.StepStatePredicates, workflowStatePredicate{predicate.Step, nonNilStrings(predicate.Outcomes), predicate.MinAttempts})
		output.stateFeatures = append(output.stateFeatures, "outcome-matching")
		if predicate.MinAttempts != nil {
			output.stateFeatures = append(output.stateFeatures, "attempt-counts")
		}
	}
	output.objectiveAddresses = append(output.objectiveAddresses, objectives...)
	return result
}
func (state *compilerState) compileWorkflowStep(source workflowStepSource, name, owner string, output *workflowCompilation) workflowRuntimeStep {
	result := workflowRuntimeStep{Name: name, StepType: source.Type, ExecutionMode: source.ExecutionMode, ProcedureRef: source.ProcedureRef, ScaffoldRefs: nonNilStrings(source.ScaffoldRefs), AllowedActionFamilies: nonNilStrings(source.AllowedActionFamilies), ToolAffordanceRefs: nonNilStrings(source.ToolAffordanceRefs), CapabilityRefs: nonNilStrings(source.CapabilityRefs), FactBindingRefs: nonNilStrings(source.FactBindingRefs), NextStep: source.Next, OnSuccess: source.OnSuccess, OnFailure: source.OnFailure, OnExhausted: source.OnExhausted, ThenStep: source.Then, ElseStep: source.Else, SwitchCases: []workflowSwitchCase{}, DefaultStep: source.Default, Branches: nonNilStrings(source.Branches), JoinStep: source.Join, OwningParallelStep: output.payload.JoinOwners[name], MaxAttempts: source.MaxAttempts, StateContract: workflowStateContract(source.Type)}
	if result.ExecutionMode == "" {
		result.ExecutionMode = "scripted"
	}
	output.payload.ControlEdges[name] = workflowEdges(source)
	if feature := map[string]string{termDecision: termDecision, termSwitch: termSwitch, termParallel: "parallel-barrier", termRetry: termRetry, termCall: termCall}[source.Type]; feature != "" {
		output.features = append(output.features, feature)
	}
	if source.ExecutionMode == termObjective || source.ExecutionMode == "scaffolded" {
		output.features = append(output.features, source.ExecutionMode+"-steps")
	}
	state.compileWorkflowStepReferences(source, name, owner, output, &result)
	if source.When != nil {
		predicate := state.compileWorkflowPredicate(*source.When, state.address(owner, "step", name), output)
		result.Predicate = &predicate
		output.payload.StepAssertionAddresses[name] = predicate.AssertionAddresses
		output.payload.StepPredicateAddresses[name] = dedupe(append(append([]string{}, predicate.AssertionAddresses...), predicate.ObjectiveAddresses...))
	} else if source.Type == termSwitch {
		assertions, predicates := []string{}, []string{}
		for i, item := range source.Cases {
			predicate := state.compileWorkflowPredicate(item.When, state.address(owner, "step", name, "case", strconv.Itoa(i)), output)
			assertions = append(assertions, predicate.AssertionAddresses...)
			predicates = append(predicates, predicate.AssertionAddresses...)
			predicates = append(predicates, predicate.ObjectiveAddresses...)
			result.SwitchCases = append(result.SwitchCases, workflowSwitchCase{i, predicate, item.Next})
		}
		if len(assertions) > 0 {
			output.payload.StepAssertionAddresses[name] = dedupe(assertions)
		}
		if len(predicates) > 0 {
			output.payload.StepPredicateAddresses[name] = dedupe(predicates)
		}
	}
	if source.OnFailure != "" || source.OnExhausted != "" {
		output.features = append(output.features, "failure-transitions")
	}
	return result
}
func (state *compilerState) compileWorkflowStepReferences(source workflowStepSource, name, owner string, output *workflowCompilation, result *workflowRuntimeStep) {
	if source.Objective != "" {
		addresses, local := state.namedReferences(termObjectives, termEvaluation, termObjective, []string{source.Objective}, referenceFindingContext{owner: owner, domain: termOrchestration, code: "orchestration.objective-ref", label: termObjective})
		output.diagnostics = append(output.diagnostics, local...)
		output.objectiveAddresses = append(output.objectiveAddresses, addresses...)
		if len(addresses) > 0 {
			result.ObjectiveAddress = addresses[0]
		}
	} else if source.Workflow != "" {
		addresses, local := state.namedReferences(termWorkflows, termOrchestration, termWorkflow, []string{source.Workflow}, referenceFindingContext{owner: owner, domain: termOrchestration, code: "orchestration.workflow-ref", label: termWorkflow})
		output.diagnostics = append(output.diagnostics, local...)
		if len(addresses) > 0 {
			result.CalledWorkflowAddress = addresses[0]
		}
	}
	if source.CompensateWith != "" {
		addresses, local := state.namedReferences(termWorkflows, termOrchestration, termWorkflow, []string{source.CompensateWith}, referenceFindingContext{owner: owner, domain: termOrchestration, code: "orchestration.workflow-ref", label: termWorkflow})
		output.diagnostics = append(output.diagnostics, local...)
		if len(addresses) > 0 {
			result.CompensationWorkflowAddress = addresses[0]
			output.payload.ExecutionContract.CompensationTargets[name] = addresses[0]
			output.features = append(output.features, "compensation")
		}
	}
}

func (state *compilerState) compileWorkflows() {
	workflows := fieldValue(state.input.model.Workflows)
	findings := []diagnostic.Diagnostic{}
	for _, name := range orderedNames(workflows, state.names(termWorkflows)) {
		findings = append(findings, state.compileWorkflow(name)...)
		if state.err != nil {
			return
		}
	}
	state.addDiagnostics(findings)
}
func sortedTerms(input []string) []string {
	result := append([]string{}, input...)
	slices.Sort(result)
	return slices.Compact(result)
}

func (state *compilerState) workflowExecutionOptions(name string, output *workflowCompilation) {
	workflow := fieldValue(state.input.model.Workflows)[name]
	if raw := fieldValue(workflow.Timeout); len(raw) > 0 && string(raw) != termNull {
		var timeout struct {
			Seconds *json.Number `json:"seconds"`
		}
		if err := json.Unmarshal(raw, &timeout); err != nil {
			state.err = invalidCompiled()
			return
		}
		output.payload.ExecutionContract.TimeoutSeconds = timeout.Seconds
	}
	if raw := fieldValue(workflow.Compensation); len(raw) > 0 && string(raw) != termNull {
		var policy struct {
			Mode          string   `json:"mode"`
			On            []string `json:"on"`
			Order         string   `json:"order"`
			FailurePolicy string   `json:"failure_policy"`
		}
		if err := json.Unmarshal(raw, &policy); err != nil {
			state.err = invalidCompiled()
			return
		}
		execution := &output.payload.ExecutionContract
		execution.CompensationMode = policy.Mode
		execution.CompensationTriggers = nonNilStrings(policy.On)
		execution.CompensationOrdering = policy.Order
		execution.CompensationFailurePolicy = policy.FailurePolicy
	}
}

func (state *compilerState) workflowStepSources(sources map[string]json.RawMessage, stepNames []string, output *workflowCompilation) map[string]workflowStepSource {
	steps := map[string]workflowStepSource{}
	for _, stepName := range stepNames {
		var source workflowStepSource
		if err := json.Unmarshal(sources[stepName], &source); err != nil {
			state.err = invalidCompiled()
			return nil
		}
		steps[stepName] = source
		if source.Type == termParallel && source.Join != "" {
			output.payload.JoinOwners[source.Join] = stepName
		}
	}
	return steps
}

func (state *compilerState) compileWorkflowSteps(steps map[string]workflowStepSource, stepNames []string, owner string, timeout bool, output *workflowCompilation) {
	for _, stepName := range stepNames {
		source := steps[stepName]
		step := state.compileWorkflowStep(source, stepName, owner, output)
		output.payload.ControlSteps[stepName] = step
		execution := &output.payload.ExecutionContract
		execution.Steps[stepName] = step.StateContract
		execution.StepTypes[stepName] = step.StepType
		if step.CalledWorkflowAddress != "" {
			execution.CallSteps[stepName] = step.CalledWorkflowAddress
		}
		if timeout {
			output.features = append(output.features, "timeouts")
		}
		if execution.CompensationMode != termDisabled {
			output.features = append(output.features, "compensation")
		}
	}
}

func (state *compilerState) compileWorkflow(name string) []diagnostic.Diagnostic {
	workflow := fieldValue(state.input.model.Workflows)[name]
	owner := state.address(termOrchestration, termWorkflow, name)
	sources := fieldValue(workflow.Steps)
	stepNames := orderedNames(sources, state.input.order["/workflows/"+escapePointer(name)+"/steps"])
	output := workflowCompilation{payload: workflowPayload{Name: name, Spec: rawJSON(workflow), StartStep: fieldValue(workflow.Start), ControlSteps: map[string]workflowRuntimeStep{}, ControlEdges: map[string][]string{}, JoinOwners: map[string]string{}, StepAssertionAddresses: map[string][]string{}, StepPredicateAddresses: map[string][]string{}, StateSchemaVersion: workflowStateVersion}}
	output.payload.ExecutionContract = workflowExecution{StateSchemaVersion: workflowStateVersion, StartStep: output.payload.StartStep, Steps: map[string]workflowStepState{}, StepTypes: map[string]string{}, CallSteps: map[string]string{}, CompensationTargets: map[string]string{}, CompensationMode: termDisabled, CompensationTriggers: []string{}, CompensationOrdering: "reverse_completion", CompensationFailurePolicy: "fail_workflow"}
	state.workflowExecutionOptions(name, &output)
	if state.err != nil {
		return nil
	}
	steps := state.workflowStepSources(sources, stepNames, &output)
	if state.err != nil {
		return nil
	}

	state.compileWorkflowSteps(steps, stepNames, owner, workflow.Timeout.Present() && !workflow.Timeout.Null(), &output)
	observables := map[string]workflowStepState{}
	usesAssertions := false
	for _, stepName := range stepNames {
		step := output.payload.ControlSteps[stepName]
		if step.StateContract.StateObservable {
			observables[stepName] = step.StateContract
		}
		output.predicateAddresses = append(output.predicateAddresses, output.payload.StepPredicateAddresses[stepName]...)
		usesAssertions = usesAssertions || len(output.payload.StepAssertionAddresses[stepName]) > 0
	}
	objectives := dedupe(output.objectiveAddresses)
	output.payload.ReferencedObjectiveAddresses = objectives
	output.payload.RequiredFeatures = sortedTerms(output.features)
	output.payload.RequiredStatePredicateFeatures = sortedTerms(output.stateFeatures)
	output.payload.ResultContract = workflowResult{workflowStateVersion, observables}
	execution := &output.payload.ExecutionContract
	execution.ControlEdges = output.payload.ControlEdges
	execution.JoinOwners = output.payload.JoinOwners
	execution.ObservableSteps = slices.Sorted(maps.Keys(observables))
	if execution.ObservableSteps == nil {
		execution.ObservableSteps = []string{}
	}
	refresh := dedupe(append(append([]string{}, objectives...), dedupe(output.predicateAddresses)...))
	state.model.Resources = append(state.model.Resources, Resource{Address: owner, Name: name, Domain: termOrchestration, Kind: termWorkflow, OrderingDependencies: []string{}, RefreshDependencies: refresh, RequiredFeatures: output.payload.RequiredFeatures, WorkflowStatePredicateFeatures: output.payload.RequiredStatePredicateFeatures, UsesAssertionRefs: usesAssertions, Payload: state.payload(output.payload)})
	return output.diagnostics
}

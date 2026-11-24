package authoring

import (
	"fmt"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

type semanticWorkflowCalls struct {
	calls, compensation   map[string][]string
	targets, compensating map[string]bool
}
type semanticWorkflowCheck struct {
	model          *semanticModel
	collector      *semanticCollector
	workflow       semanticWorkflow
	edges          map[string][]string
	joins          map[string][]string
	joinOrder      []string
	predicates     map[string][]string
	predicateOrder []string
	predecessors   map[string][]string
	reachable      map[string]bool
}

func (m *semanticModel) checkWorkflows(c *semanticCollector) {
	calls := semanticWorkflowCalls{calls: map[string][]string{}, compensation: map[string][]string{}, targets: map[string]bool{}, compensating: map[string]bool{}}
	for _, workflow := range m.workflows {
		w := semanticWorkflowCheck{model: m, collector: c, workflow: workflow, edges: map[string][]string{}, joins: map[string][]string{}, predicates: map[string][]string{}, predecessors: map[string][]string{}}
		w.build(&calls)
		w.check()
	}
	if graph.HasCycle(calls.calls) {
		c.report(semanticOwner{}, "Workflow call graph contains a cycle")
	}
	combined := map[string][]string{}
	for _, workflow := range m.workflows {
		combined[workflow.name] = append(slices.Clone(calls.calls[workflow.name]), calls.compensation[workflow.name]...)
	}
	if graph.HasCycle(combined) {
		c.report(semanticOwner{}, "Combined workflow call/compensation graph contains a cycle")
	}
	var targets []string
	for name := range calls.targets {
		targets = append(targets, name)
	}
	slices.Sort(targets)
	for _, name := range targets {
		if calls.compensating[name] {
			c.report(semanticOwner{workflowsSection, name}, fmt.Sprintf("Workflow '%s' cannot be used as a compensation workflow because it also declares compensate-with steps", name))
		}
	}
}
func (w *semanticWorkflowCheck) report(message string) {
	w.collector.report(semanticOwner{workflowsSection, w.workflow.name}, message)
}
func (w *semanticWorkflowCheck) label(step string) string {
	return fmt.Sprintf("Workflow '%s' step '%s'", w.workflow.name, step)
}
func (w *semanticWorkflowCheck) target(step, field, ref string) string {
	if ref == "" || variable(ref) {
		return ""
	}
	if _, present := w.workflow.steps[ref]; !present {
		w.report(fmt.Sprintf("%s %s step '%s' is not defined", w.label(step), field, ref))
		return ""
	}
	return ref
}
func (w *semanticWorkflowCheck) edge(step, field, ref string) {
	if resolved := w.target(step, field, ref); resolved != "" {
		w.edges[step] = append(w.edges[step], resolved)
	}
}
func (w *semanticWorkflowCheck) build(calls *semanticWorkflowCalls) {
	if _, present := w.workflow.steps[w.workflow.start]; !present && !variable(w.workflow.start) {
		w.report(fmt.Sprintf("Workflow '%s' start step '%s' is not defined", w.workflow.name, w.workflow.start))
	}
	for _, name := range w.workflow.order {
		w.edges[name] = nil
	}
	for _, name := range w.workflow.order {
		if strings.Contains(name, ".") {
			w.report(fmt.Sprintf("Workflow '%s' step '%s' cannot contain '.' because objective windows use '<workflow>.<step>' syntax", w.workflow.name, name))
		}
		w.step(name, w.workflow.steps[name], calls)
	}
}
func (w *semanticWorkflowCheck) step(name string, step semanticWorkflowStep, calls *semanticWorkflowCalls) {
	switch step.Type {
	case objectiveStep, retryStep:
		if !variable(step.Objective) && !w.model.definitions[objectivesSection][step.Objective] {
			w.report(fmt.Sprintf("%s references undefined objective '%s'", w.label(name), step.Objective))
		}
		w.realization(name, step)
		if step.Type == retryStep {
			w.edge(name, "on-success", step.Success)
			w.edge(name, "on-exhausted", step.Exhausted)
		} else {
			w.terminator(name, step, calls)
		}
	case callStep:
		if !variable(step.Workflow) {
			if !w.model.definitions[workflowsSection][step.Workflow] {
				w.report(fmt.Sprintf("%s references undefined workflow '%s'", w.label(name), step.Workflow))
			} else {
				calls.calls[w.workflow.name] = append(calls.calls[w.workflow.name], step.Workflow)
			}
		}
		w.terminator(name, step, calls)
	case decisionTerm:
		if step.When != nil {
			w.addPredicate(name, name, *step.When)
		}
		w.edge(name, "then", step.Then)
		w.edge(name, "else", step.Else)
	case switchType:
		w.switchStep(name, step)
	case parallelStepType:
		w.parallelStep(name, step)
	case joinStepType:
		w.edge(name, "next", step.Next)
	}
}
func (w *semanticWorkflowCheck) terminator(name string, step semanticWorkflowStep, calls *semanticWorkflowCalls) {
	w.edge(name, "on-success", step.Success)
	w.edge(name, "on-failure", step.Failure)
	if step.Compensation == "" {
		return
	}
	calls.compensating[w.workflow.name] = true
	if variable(step.Compensation) {
		return
	}
	if !w.model.definitions[workflowsSection][step.Compensation] {
		w.report(fmt.Sprintf("%s references undefined compensation workflow '%s'", w.label(name), step.Compensation))
	} else {
		calls.compensation[w.workflow.name] = append(calls.compensation[w.workflow.name], step.Compensation)
		calls.targets[step.Compensation] = true
	}
}
func (w *semanticWorkflowCheck) switchStep(name string, step semanticWorkflowStep) {
	for i, row := range step.Cases {
		w.addPredicate(name, fmt.Sprintf("%s.case[%d]", name, i), row.When)
		w.edge(name, fmt.Sprintf("case[%d] next", i), row.Next)
	}
	w.edge(name, "default", step.Default)
}
func (w *semanticWorkflowCheck) parallelStep(name string, step semanticWorkflowStep) {
	for _, branch := range step.Branches {
		w.edge(name, "branch", branch)
	}
	if join := w.target(name, "join", step.Join); join != "" {
		if w.joins[join] == nil {
			w.joinOrder = append(w.joinOrder, join)
		}
		w.joins[join] = append(w.joins[join], name)
	}
	w.edge(name, "on-failure", step.Failure)
}
func (w *semanticWorkflowCheck) check() {
	w.checkJoins()
	if graph.HasCycle(w.edges) {
		w.report(fmt.Sprintf("Workflow '%s' graph contains a cycle", w.workflow.name))
	}
	if _, present := w.workflow.steps[w.workflow.start]; !present || variable(w.workflow.start) {
		return
	}
	w.reachable = workflowClosure(w.edges, []string{w.workflow.start}, "")
	var unreachable []string
	for _, name := range w.workflow.order {
		if !w.reachable[name] {
			unreachable = append(unreachable, name)
		}
	}
	if len(unreachable) > 0 {
		slices.Sort(unreachable)
		w.report(fmt.Sprintf("Workflow '%s' contains unreachable steps: %s", w.workflow.name, strings.Join(unreachable, ", ")))
	}
	w.buildPredecessors()
	w.checkJoinClosures()
	w.checkPredicateAvailability()
	w.checkConvergence()
}
func (w *semanticWorkflowCheck) buildPredecessors() {
	for _, from := range w.workflow.order {
		if !w.reachable[from] {
			continue
		}
		for _, to := range w.edges[from] {
			if w.reachable[to] && !slices.Contains(w.predecessors[to], from) {
				w.predecessors[to] = append(w.predecessors[to], from)
			}
		}
	}
}
func (w *semanticWorkflowCheck) checkJoins() {
	for _, name := range w.joinOrder {
		if w.workflow.steps[name].Type != joinStepType {
			w.report(fmt.Sprintf("Workflow '%s' step '%s' is used as a parallel join but is not a join step", w.workflow.name, name))
		}
		if len(w.joins[name]) > 1 {
			w.report(fmt.Sprintf("Workflow '%s' join step '%s' may only be targeted by one parallel step", w.workflow.name, name))
		}
	}
	for _, name := range w.workflow.order {
		if w.workflow.steps[name].Type == joinStepType && len(w.joins[name]) == 0 {
			w.report(fmt.Sprintf("Workflow '%s' join step '%s' is not referenced by any parallel step", w.workflow.name, name))
		}
	}
}
func (w *semanticWorkflowCheck) checkJoinClosures() {
	for _, name := range w.workflow.order {
		step := w.workflow.steps[name]
		if step.Type != parallelStepType || !w.reachable[step.Join] || variable(step.Join) {
			continue
		}
		w.checkJoinClosure(step)
	}
}
func (w *semanticWorkflowCheck) checkJoinClosure(step semanticWorkflowStep) {
	var branches []string
	for _, ref := range step.Branches {
		if w.reachable[ref] {
			branches = append(branches, ref)
		}
	}
	closure := workflowClosure(w.edges, branches, step.Join)
	var foreign []string
	for _, predecessor := range w.predecessors[step.Join] {
		if !closure[predecessor] {
			foreign = append(foreign, predecessor)
		}
	}
	if len(foreign) > 0 {
		slices.Sort(foreign)
		w.report(fmt.Sprintf("Workflow '%s' join step '%s' may only be entered from the owning parallel's branch closure; unexpected predecessors: %s", w.workflow.name, step.Join, strings.Join(foreign, ", ")))
	}
}

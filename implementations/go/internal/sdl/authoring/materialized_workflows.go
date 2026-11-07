package authoring

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

type workflowGraph struct {
	root                materializedChecks
	steps               map[string]any
	edges, predecessors map[string][]string
	joins               map[string]string
	predicates          map[string][]string
	start               string
}

type workflowCalls struct {
	root                  materializedChecks
	combined              map[string][]string
	compensating, targets map[string]bool
}

func (c materializedChecks) workflows() error {
	calls := workflowCalls{root: c, combined: map[string][]string{}, compensating: map[string]bool{}, targets: map[string]bool{}}
	for name, raw := range object(c.value[workflowsSection]) {
		workflow := object(raw)
		w := workflowGraph{root: c, steps: object(workflow["steps"]), edges: map[string][]string{}, predecessors: map[string][]string{}, joins: map[string]string{}, predicates: map[string][]string{}, start: text(workflow["start"])}
		if err := w.build(name, &calls); err != nil {
			return err
		}
		if err := w.check(); err != nil {
			return err
		}
	}
	if graph.HasCycle(calls.combined) {
		return semanticInvalid()
	}
	for target := range calls.targets {
		if calls.compensating[target] {
			return semanticInvalid()
		}
	}
	return nil
}
func (w *workflowGraph) build(name string, calls *workflowCalls) error {
	for stepName, raw := range w.steps {
		step := object(raw)
		if strings.Contains(stepName, ".") {
			return semanticInvalid()
		}
		if err := w.step(stepName, step); err != nil {
			return err
		}
		if err := calls.step(name, step); err != nil {
			return err
		}
	}
	return nil
}
func (c *workflowCalls) step(name string, step map[string]any) error {
	if step["type"] == callStep {
		if err := c.edge(name, text(step["workflow"])); err != nil {
			return err
		}
	}
	if step["type"] != callStep && step["type"] != objectiveStep {
		return nil
	}
	target := text(step["compensate_with"])
	if target == "" {
		return nil
	}
	c.compensating[name] = true
	if err := c.edge(name, target); err != nil {
		return err
	}
	if !variable(target) {
		c.targets[target] = true
	}
	return nil
}
func (c *workflowCalls) edge(name, target string) error {
	if err := referencesPresent([]any{target}, object(c.root.value[workflowsSection])); err != nil {
		return err
	}
	if !variable(target) {
		c.combined[name] = append(c.combined[name], target)
	}
	return nil
}

func (w *workflowGraph) step(name string, step map[string]any) error {
	w.edges[name] = []string{}
	fields := map[string][]string{objectiveStep: {onSuccessField, onFailureField}, callStep: {onSuccessField, onFailureField}, decisionTerm: {"then", "else"}, "switch": {defaultField}, parallelStepType: {onFailureField}, retryStep: {onSuccessField, "on_exhausted"}, joinStepType: {"next"}}[text(step["type"])]
	for _, field := range fields {
		if err := w.edge(name, text(step[field])); err != nil {
			return err
		}
	}
	if step["type"] == objectiveStep || step["type"] == retryStep {
		if err := referencesPresent([]any{step[objectiveStep]}, object(w.root.value[objectivesSection])); err != nil {
			return err
		}
		if err := w.root.workflowRealization(step); err != nil {
			return err
		}
	}
	return w.branchStep(name, step)
}
func (w *workflowGraph) branchStep(name string, step map[string]any) error {
	switch step["type"] {
	case decisionTerm:
		return w.predicate(name, object(step["when"]))
	case "switch":
		for _, raw := range array(step["cases"]) {
			branch := object(raw)
			if err := w.edge(name, text(branch["next"])); err != nil {
				return err
			}
			if err := w.predicate(name, object(branch["when"])); err != nil {
				return err
			}
		}
	case parallelStepType:
		return w.parallelStep(name, step)
	}
	return nil
}
func (w *workflowGraph) edge(from, to string) error {
	if to == "" || variable(to) {
		return nil
	}
	if w.steps[to] == nil {
		return semanticInvalid()
	}
	w.edges[from] = append(w.edges[from], to)
	w.predecessors[to] = append(w.predecessors[to], from)
	return nil
}
func (w *workflowGraph) check() error {
	if graph.HasCycle(w.edges) {
		return semanticInvalid()
	}
	for name, raw := range w.steps {
		if object(raw)["type"] == joinStepType && w.joins[name] == "" {
			return semanticInvalid()
		}
	}
	if variable(w.start) {
		return nil
	}
	if w.steps[w.start] == nil {
		return semanticInvalid()
	}
	if len(workflowClosure(w.edges, []string{w.start}, "")) != len(w.steps) {
		return semanticInvalid()
	}
	order, err := graph.Order(w.edges, nil)
	if err != nil {
		return err
	}
	if err = w.parallelChecks(order); err != nil {
		return err
	}
	return w.predicateAvailability(order)
}
func workflowClosure(edges map[string][]string, roots []string, stop string) map[string]bool {
	seen := map[string]bool{}
	pending := append([]string(nil), roots...)
	for len(pending) > 0 {
		node := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if node == stop || seen[node] {
			continue
		}
		seen[node] = true
		pending = append(pending, edges[node]...)
	}
	return seen
}

func (w *workflowGraph) parallelStep(name string, step map[string]any) error {
	for _, branch := range array(step["branches"]) {
		if err := w.edge(name, text(branch)); err != nil {
			return err
		}
	}
	join := text(step[joinStepType])
	if !variable(join) {
		if object(w.steps[join])["type"] != joinStepType || w.joins[join] != "" {
			return semanticInvalid()
		}
		w.joins[join] = name
	}
	return nil
}

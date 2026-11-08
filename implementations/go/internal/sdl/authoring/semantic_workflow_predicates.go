package authoring

import (
	"fmt"
	"slices"
	"strings"
)

func (w *semanticWorkflowCheck) addPredicate(name, label string, predicate semanticWorkflowPredicate) {
	if _, present := w.predicates[name]; !present {
		w.predicateOrder = append(w.predicateOrder, name)
		w.predicates[name] = nil
	}
	w.predicateSectionReferences(label, predicate)
	for _, row := range predicate.Steps {
		if variable(row.Step) {
			continue
		}
		if w.predicateState(label, row.Step, row.Outcomes) {
			w.predicates[name] = append(w.predicates[name], row.Step)
		}
	}
}
func (w *semanticWorkflowCheck) predicateSectionReferences(label string, predicate semanticWorkflowPredicate) {
	assertions := fieldValue(w.model.transport.Assertions)
	for _, ref := range predicate.Assertions {
		if variable(ref) {
			continue
		}
		assertion, present := assertions[ref]
		switch {
		case !present:
			w.report(fmt.Sprintf("%s references undefined assertion '%s' in predicate", w.label(label), ref))
		case string(fieldValue(assertion.Role)) != "precondition":
			w.report(fmt.Sprintf("%s assertion '%s' in predicate must be a precondition", w.label(label), ref))
		}
	}
	for _, ref := range predicate.Objectives {
		if !variable(ref) && !w.model.definitions[objectivesSection][ref] {
			w.report(fmt.Sprintf("%s references undefined objective '%s' in predicate", w.label(label), ref))
		}
	}
}
func (w *semanticWorkflowCheck) predicateState(label, ref string, outcomes []string) bool {
	step, present := w.workflow.steps[ref]
	switch {
	case !present:
		w.report(fmt.Sprintf("%s references undefined step state '%s' in predicate", w.label(label), ref))
		return false
	case ref == label:
		w.report(w.label(label) + " cannot reference its own state in a predicate")
		return false
	case len(workflowOutcomes(step.Type)) == 0:
		w.report(fmt.Sprintf("%s cannot reference non-executable step '%s' in a predicate", w.label(label), ref))
		return false
	}
	allowed := workflowOutcomes(step.Type)
	var invalid []string
	for _, outcome := range outcomes {
		if !slices.Contains(allowed, outcome) {
			invalid = append(invalid, outcome)
		}
	}
	if len(invalid) > 0 {
		w.report(fmt.Sprintf("%s references step '%s' with impossible outcomes ['%s']; allowed outcomes are: %s", w.label(label), ref, strings.Join(invalid, "', '"), strings.Join(allowed, ", ")))
		return false
	}
	return true
}

// Query one state at a time so storage grows with the workflow graph rather
// than with every possible pair of executable steps. Visiting sets also make
// the analysis total when a separately reported graph cycle is present.
type semanticStateQuery struct {
	workflow         *semanticWorkflowCheck
	ref              string
	before, visiting map[string]bool
}

func (w *semanticWorkflowCheck) checkPredicateAvailability() {
	var query *semanticStateQuery
	for _, name := range w.predicateOrder {
		if !w.reachable[name] {
			continue
		}
		for _, ref := range w.predicates[name] {
			if query == nil || query.ref != ref {
				query = &semanticStateQuery{workflow: w, ref: ref, before: map[string]bool{}, visiting: map[string]bool{}}
			}
			if !query.available(name) {
				w.report(fmt.Sprintf("%s references step state '%s' that is not guaranteed to be known before this predicate", w.label(name), ref))
			}
		}
	}
}
func (q *semanticStateQuery) available(name string) bool {
	if result, present := q.before[name]; present {
		return result
	}
	if q.visiting[name] {
		return false
	}
	q.visiting[name] = true
	result := false
	if name != q.workflow.workflow.start {
		if q.workflow.workflow.steps[name].Type == joinStepType && len(q.workflow.joins[name]) > 0 {
			result = q.join(name)
		} else {
			result = q.incoming(name)
		}
	}
	delete(q.visiting, name)
	q.before[name] = result
	return result
}
func (q *semanticStateQuery) incoming(name string) bool {
	pred := q.workflow.predecessors[name]
	result := len(pred) > 0
	for _, predecessor := range pred {
		step := q.workflow.workflow.steps[predecessor]
		produced := predecessor == q.ref && (step.Type == objectiveStep || step.Type == retryStep || step.Type == callStep || step.Type == parallelStepType && step.Failure == name)
		// Evaluate every predecessor, as the reference computes all incoming
		// sets before taking their intersection.
		available := q.available(predecessor)
		result = result && (available || produced)
	}
	return result
}
func (q *semanticStateQuery) join(name string) bool {
	w := q.workflow
	owner := w.joins[name][0]
	result := q.available(owner) || owner == q.ref
	for _, branch := range w.workflow.steps[owner].Branches {
		if _, present := w.workflow.steps[branch]; !present {
			continue
		}
		known := w.branchState(branch, name, q.ref, map[string]bool{}, map[string]bool{})
		result = result || known
	}
	return result
}
func (w *semanticWorkflowCheck) branchState(node, join, ref string, memo, visiting map[string]bool) bool {
	if node == join {
		return false
	}
	if result, present := memo[node]; present {
		return result
	}
	if visiting[node] {
		return false
	}
	visiting[node] = true
	successors := w.edges[node]
	result := len(successors) > 0
	for _, successor := range successors {
		known := w.branchState(successor, join, ref, memo, visiting)
		result = result && known
	}
	result = result || node == ref && len(workflowOutcomes(w.workflow.steps[node].Type)) > 0
	delete(visiting, node)
	memo[node] = result
	return result
}
func (w *semanticWorkflowCheck) checkConvergence() {
	for _, name := range w.workflow.order {
		step := w.workflow.steps[name]
		if step.Type != parallelStepType || variable(step.Join) {
			continue
		}
		if _, present := w.workflow.steps[step.Join]; !present {
			continue
		}
		for _, branch := range step.Branches {
			if _, present := w.workflow.steps[branch]; !present || variable(branch) {
				continue
			}
			if !w.converges(branch, step.Join, map[string]bool{}, map[string]bool{}) {
				w.report(fmt.Sprintf("Workflow '%s' parallel step '%s' requires every explicit branch path from '%s' to converge on join '%s'", w.workflow.name, name, branch, step.Join))
			}
		}
	}
}
func (w *semanticWorkflowCheck) converges(node, join string, memo, visiting map[string]bool) bool {
	if node == join {
		return true
	}
	if result, present := memo[node]; present {
		return result
	}
	if visiting[node] {
		return false
	}
	visiting[node] = true
	result := len(w.edges[node]) > 0
	for _, successor := range w.edges[node] {
		if !w.converges(successor, join, memo, visiting) {
			result = false
			break
		}
	}
	delete(visiting, node)
	memo[node] = result
	return result
}

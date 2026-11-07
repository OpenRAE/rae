package authoring

import "slices"

func workflowOutcomes(kind string) []string {
	switch kind {
	case objectiveStep, callStep, parallelStepType:
		return []string{"succeeded", "failed"}
	case retryStep:
		return []string{"succeeded", "exhausted"}
	default:
		return nil
	}
}
func (w *workflowGraph) predicate(name string, predicate map[string]any) error {
	if err := w.root.assertionRole(array(predicate[assertionsSection]), "precondition"); err != nil {
		return err
	}
	if err := referencesPresent(array(predicate[objectivesSection]), object(w.root.value[objectivesSection])); err != nil {
		return err
	}
	for _, raw := range array(predicate["steps"]) {
		state := object(raw)
		ref := text(state["step"])
		if variable(ref) {
			continue
		}
		allowed := workflowOutcomes(text(object(w.steps[ref])["type"]))
		if ref == name || len(allowed) == 0 {
			return semanticInvalid()
		}
		for _, outcome := range array(state["outcomes"]) {
			if !slices.Contains(allowed, text(outcome)) {
				return semanticInvalid()
			}
		}
		w.predicates[name] = append(w.predicates[name], ref)
	}
	return nil
}
func (w *workflowGraph) parallelChecks(order []string) error {
	for join, owner := range w.joins {
		if err := w.parallelCheck(join, owner, order); err != nil {
			return err
		}
	}
	return nil
}
func (w *workflowGraph) parallelCheck(join, owner string, order []string) error {
	branches := concreteRefs(array(object(w.steps[owner])["branches"]))
	closure := workflowClosure(w.edges, branches, join)
	for _, predecessor := range w.predecessors[join] {
		if !closure[predecessor] {
			return semanticInvalid()
		}
	}
	converges := map[string]bool{join: true}
	for _, node := range order {
		if node == join {
			continue
		}
		yes := len(w.edges[node]) > 0
		for _, successor := range w.edges[node] {
			yes = yes && converges[successor]
		}
		converges[node] = yes
	}
	for _, branch := range branches {
		if !converges[branch] {
			return semanticInvalid()
		}
	}
	return nil
}

// Check one requested state at a time. Storage grows with the graph, rather
// than with the square of its executable-state count.
func (w *workflowGraph) predicateAvailability(order []string) error {
	for name, refs := range w.predicates {
		for _, ref := range refs {
			if !w.availableState(ref, order)[name] {
				return semanticInvalid()
			}
		}
	}
	return nil
}
func (w *workflowGraph) availableState(ref string, order []string) map[string]bool {
	before := map[string]bool{}
	for _, node := range slices.Backward(order) {
		if node == w.start {
			continue
		}
		if owner := w.joins[node]; owner != "" {
			available := before[owner] || owner == ref
			for _, branch := range concreteRefs(array(object(w.steps[owner])["branches"])) {
				available = available || w.branchHasState(branch, node, ref, order)
			}
			before[node] = available
		} else {
			before[node] = w.incomingState(node, ref, before)
		}
	}
	return before
}
func (w *workflowGraph) incomingState(node, ref string, before map[string]bool) bool {
	available := len(w.predecessors[node]) > 0
	for _, predecessor := range w.predecessors[node] {
		step := object(w.steps[predecessor])
		produced := predecessor == ref && (step["type"] == objectiveStep || step["type"] == retryStep || step["type"] == callStep || step["type"] == parallelStepType && text(step[onFailureField]) == node)
		available = available && (before[predecessor] || produced)
	}
	return available
}

func (w *workflowGraph) branchHasState(branch, join, ref string, order []string) bool {
	guaranteed := map[string]bool{}
	for _, node := range order {
		if node == join {
			continue
		}
		yes := len(w.edges[node]) > 0
		for _, successor := range w.edges[node] {
			yes = yes && guaranteed[successor]
		}
		guaranteed[node] = yes || node == ref && len(workflowOutcomes(text(object(w.steps[node])["type"]))) > 0
	}
	return guaranteed[branch]
}

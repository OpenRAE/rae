package comparison

import "slices"

type pathCursor struct {
	identity string
	steps    []pathStep
}

func impactPaths(input request, changes []change, dependencies []dependencyChange, reasons reasonSet) []impactPath {
	adjacency := impactAdjacency(dependencies)
	sources := []string{}
	for _, change := range changes {
		if change.IdentityRelation != relationSame || change.Semantic == relationChanged || change.Structural == relationChanged {
			sources = append(sources, change.Identity)
		}
	}
	slices.Sort(sources)
	paths := []impactPath{}
	for _, source := range sources {
		var exhausted bool
		paths, exhausted = sourcePaths(input, source, adjacency, paths, reasons)
		if exhausted {
			break
		}
	}
	slices.SortFunc(paths, comparePaths)
	return paths
}
func impactAdjacency(input []dependencyChange) map[string][]pathStep {
	result := map[string][]pathStep{}
	for _, edge := range input {
		state, side := edge.After, "after"
		if state == nil {
			state, side = edge.Before, "before"
		}
		if state == nil {
			continue
		}
		result[state.Identity] = append(result[state.Identity], pathStep{Dependent: edge.Dependent, Dependency: state.Identity, Rule: edge.Rule, Version: "1", Side: side})
	}
	for key, steps := range result {
		slices.SortStableFunc(steps, func(a, b pathStep) int {
			return compareTuple([]string{a.Dependent, a.Rule}, []string{b.Dependent, b.Rule})
		})
		result[key] = steps
	}
	return result
}
func sourcePaths(input request, source string, adjacency map[string][]pathStep, paths []impactPath, reasons reasonSet) ([]impactPath, bool) {
	queue := []pathCursor{{source, []pathStep{}}}
	visited := map[string]bool{source: true}
	for cursor := 0; cursor < len(queue); cursor++ {
		current := queue[cursor]
		outgoing := adjacency[current.identity]
		if len(outgoing) > 0 && len(current.steps) >= input.Limits.Depth {
			reasons["impact-path-depth-exhausted"] = true
			continue
		}
		for _, step := range outgoing {
			nextSteps := append(append([]pathStep{}, current.steps...), step)
			paths = append(paths, impactPath{source, step.Dependent, nextSteps})
			// The reference appends before checking the zero-path bound.
			if len(paths) >= input.Limits.Paths {
				reasons[reasonPaths] = true
				return paths, true
			}
			if !visited[step.Dependent] {
				visited[step.Dependent] = true
				queue = append(queue, pathCursor{step.Dependent, nextSteps})
			}
		}
	}
	return paths, false
}
func comparePaths(a, b impactPath) int {
	if order := compareTuple([]string{a.Source, a.Affected}, []string{b.Source, b.Affected}); order != 0 {
		return order
	}
	for index := range min(len(a.Steps), len(b.Steps)) {
		left, right := a.Steps[index], b.Steps[index]
		if order := compareTuple([]string{left.Dependency, left.Dependent, left.Rule}, []string{right.Dependency, right.Dependent, right.Rule}); order != 0 {
			return order
		}
	}
	return len(a.Steps) - len(b.Steps)
}

package analysis

import (
	"context"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

type opacityTransition struct {
	Ordinal int `json:"ordinal"`
	Source  int `json:"source_state_ordinal"`
	Target  int `json:"target_state_ordinal"`
}
type opacityReachability struct {
	points      []opacityPoint
	transitions []opacityTransition
	parents     map[int]*opacityTransition
}

func reachableOpacity(ctx context.Context, points []opacityPoint, transitions []opacityTransition, initial []int) (opacityReachability, error) {
	adjacency := make([][]int, len(points))
	for index, transition := range transitions {
		adjacency[transition.Source] = append(adjacency[transition.Source], index)
	}
	parents := map[int]*opacityTransition{}
	queue := slices.Clone(initial)
	for _, ordinal := range initial {
		parents[ordinal] = nil
	}
	result := opacityReachability{points: []opacityPoint{}, transitions: []opacityTransition{}, parents: parents}
	for next := 0; next < len(queue); next++ {
		if ctx.Err() != nil {
			return opacityReachability{}, fault.New(fault.Operational, termAnalysisCancelled, nil)
		}
		source := queue[next]
		for _, index := range adjacency[source] {
			transition := transitions[index]
			result.transitions = append(result.transitions, transition)
			if _, seen := parents[transition.Target]; seen {
				continue
			}
			parents[transition.Target] = &transitions[index]
			queue = append(queue, transition.Target)
		}
	}
	slices.Sort(queue)
	for _, ordinal := range queue {
		result.points = append(result.points, points[ordinal])
	}
	return result, nil
}
func opacityCoverage(input map[string]any, points []opacityPoint, reached opacityReachability) map[string]any {
	pairs := map[[2]string]bool{}
	orders := map[string]bool{}
	evaluated, secrets := 0, 0
	perStrategy := map[string]map[string]any{}
	for _, strategy := range stringValues(object(input[termAssumptions])[termStrategyRefs]) {
		perStrategy[strategy] = map[string]any{"strategy_ref": strategy, fieldExploredStates: 0, fieldExploredTransitions: 0, termReachableEvaluationPoints: 0, termReachableSecretPoints: 0}
	}
	increment := func(row map[string]any, key string) { count, _ := row[key].(int); row[key] = count + 1 }
	for _, point := range reached.points {
		pairs[[2]string{point.Scheduler, point.Environment}] = true
		orders[point.Order] = true
		row := perStrategy[point.Strategy]
		increment(row, fieldExploredStates)
		if point.Evaluation {
			evaluated++
			increment(row, termReachableEvaluationPoints)
			if point.Secret {
				secrets++
				increment(row, termReachableSecretPoints)
			}
		}
	}
	for _, transition := range reached.transitions {
		increment(perStrategy[points[transition.Source].Strategy], fieldExploredTransitions)
	}
	rows := []any{}
	for _, strategy := range stringValues(object(input[termAssumptions])[termStrategyRefs]) {
		rows = append(rows, perStrategy[strategy])
	}
	return map[string]any{"declared": input[termDeclaredCounts], fieldExploredStates: len(reached.points), fieldExploredTransitions: len(reached.transitions), termReachableEvaluationPoints: evaluated, termReachableSecretPoints: secrets, "strategy_coverage": rows, "explored_scheduler_environment_pairs": len(pairs), "explored_order_variants": len(orders), "complete_fixed_point": true}
}
func opacityCounterexamplePath(ordinal int, parents map[int]*opacityTransition) []int {
	path := []int{}
	for parents[ordinal] != nil {
		transition := parents[ordinal]
		path = append(path, transition.Ordinal)
		ordinal = transition.Source
	}
	slices.Reverse(path)
	return path
}

// Package graph provides iterative directed-graph mechanics. Callers own
// node identities, graph construction, normalization and diagnostic messages.
package graph

import (
	"cmp"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// ErrGraph reports a missing key in a graph required to be closed.
var ErrGraph = fault.New(fault.InvalidInput, "graph-missing-node", nil)

// Less supplies the node order. Nil selects lexical order; equal keys are
// ordered by node identity so Go map iteration cannot change a result.
type Less func(string, string) bool

func normalized(input map[string][]string, closed bool) (map[string][]string, error) {
	result := make(map[string][]string, len(input))
	for node, adjacent := range input {
		result[node] = unique(adjacent)
	}
	if closed {
		if err := checkClosed(input); err != nil {
			return nil, err
		}
	} else {
		addMissing(result, input)
	}
	return result, nil
}

func unique(nodes []string) []string {
	seen := map[string]bool{}
	result := []string{}
	for _, node := range nodes {
		if !seen[node] {
			seen[node] = true
			result = append(result, node)
		}
	}
	return result
}

func checkClosed(graph map[string][]string) error {
	for _, adjacent := range graph {
		for _, neighbor := range adjacent {
			if _, exists := graph[neighbor]; !exists {
				return ErrGraph
			}
		}
	}
	return nil
}

func addMissing(result, input map[string][]string) {
	for _, adjacent := range input {
		for _, node := range adjacent {
			if _, exists := result[node]; !exists {
				result[node] = []string{}
			}
		}
	}
}

func dependencyOrder(graph map[string][]string, less Less) []string {
	nodes := slices.Collect(maps.Keys(graph))
	slices.SortFunc(nodes, comparator(less))
	dependents := map[string][]string{}
	degrees := make(map[string]int, len(graph))
	ready := []string{}
	for _, node := range nodes {
		degrees[node] = len(graph[node])
		if degrees[node] == 0 {
			ready = append(ready, node)
		}
		for _, dependency := range graph[node] {
			dependents[dependency] = append(dependents[dependency], node)
		}
	}
	for index := 0; index < len(ready); index++ {
		for _, dependent := range dependents[ready[index]] {
			degrees[dependent]--
			if degrees[dependent] == 0 {
				ready = append(ready, dependent)
			}
		}
	}
	return ready
}

// HasCycle includes nodes that appear only as adjacent nodes.
func HasCycle(input map[string][]string) bool {
	graph, _ := normalized(input, false)
	return len(dependencyOrder(graph, nil)) != len(graph)
}

// Order writes each node after its dependencies using a FIFO ready queue.
// Nodes blocked by cycles follow in node order, matching graphlib's callers.
func Order(input map[string][]string, less Less) ([]string, error) {
	graph, err := normalized(input, true)
	if err != nil {
		return nil, err
	}
	result := dependencyOrder(graph, less)
	placed := map[string]bool{}
	for _, node := range result {
		placed[node] = true
	}
	var remaining []string
	for node := range graph {
		if !placed[node] {
			remaining = append(remaining, node)
		}
	}
	slices.SortFunc(remaining, comparator(less))
	return append(result, remaining...), nil
}

type frame struct {
	node string
	next int
}

func finishOrder(graph map[string][]string, less Less) []string {
	nodes := slices.Collect(maps.Keys(graph))
	slices.SortFunc(nodes, comparator(less))
	visited := map[string]bool{}
	var finished []string
	for _, root := range nodes {
		if visited[root] {
			continue
		}
		visited[root] = true
		pending := []frame{{node: root}}
		for len(pending) > 0 {
			top := &pending[len(pending)-1]
			if top.next == len(graph[top.node]) {
				finished = append(finished, top.node)
				pending = pending[:len(pending)-1]
				continue
			}
			child := graph[top.node][top.next]
			top.next++
			if !visited[child] {
				visited[child] = true
				pending = append(pending, frame{node: child})
			}
		}
	}
	return finished
}

// Cycles returns the sorted strongly connected components containing a cycle.
// Both passes use explicit stacks, so long chains do not grow the call stack.
func Cycles(input map[string][]string, less Less) ([][]string, error) {
	graph, err := normalized(input, true)
	if err != nil {
		return nil, err
	}
	reverse := map[string][]string{}
	for node, adjacent := range graph {
		for _, neighbor := range adjacent {
			reverse[neighbor] = append(reverse[neighbor], node)
		}
	}
	visited := map[string]bool{}
	components := [][]string{}
	order := finishOrder(graph, less)
	for _, root := range slices.Backward(order) {
		if visited[root] {
			continue
		}
		component := collectComponent(root, reverse, visited)
		if len(component) > 1 || slices.Contains(graph[root], root) {
			slices.SortFunc(component, comparator(less))
			components = append(components, component)
		}
	}
	slices.SortFunc(components, func(a, b []string) int {
		return slices.CompareFunc(a, b, comparator(less))
	})
	return components, nil
}

func collectComponent(root string, reverse map[string][]string, visited map[string]bool) []string {
	visited[root] = true
	pending := []string{root}
	var component []string
	for len(pending) > 0 {
		node := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		component = append(component, node)
		for _, neighbor := range reverse[node] {
			if !visited[neighbor] {
				visited[neighbor] = true
				pending = append(pending, neighbor)
			}
		}
	}
	return component
}

func comparator(less Less) func(string, string) int {
	return func(a, b string) int {
		if less != nil {
			if less(a, b) {
				return -1
			}
			if less(b, a) {
				return 1
			}
		}
		return cmp.Compare(a, b)
	}
}

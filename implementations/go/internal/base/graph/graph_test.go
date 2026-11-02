package graph

import (
	"errors"
	"fmt"
	"slices"
	"testing"
)

func TestFIFOOrderAndCyclicComponents(t *testing.T) {
	for _, test := range []struct {
		graph  map[string][]string
		order  []string
		cycles [][]string
	}{
		{map[string][]string{}, []string{}, [][]string{}},
		{map[string][]string{"a": {}, "c": {}, "b": {"a"}}, []string{"a", "c", "b"}, [][]string{}},
		{map[string][]string{"a": {"b"}, "b": {"a"}, "c": {}, "d": {"a"}}, []string{"c", "a", "b", "d"}, [][]string{{"a", "b"}}},
		{map[string][]string{"a": {"a"}, "b": {"c"}, "c": {"b"}, "d": {"b"}}, []string{"a", "b", "c", "d"}, [][]string{{"a"}, {"b", "c"}}},
		{map[string][]string{"a": {"b", "b"}, "b": {}}, []string{"b", "a"}, [][]string{}},
	} {
		order, err := Order(test.graph, nil)
		if err != nil || !slices.Equal(order, test.order) {
			t.Errorf("Order() = %v, %v, want %v", order, err, test.order)
		}
		components, err := Cycles(test.graph, nil)
		if err != nil || !slices.EqualFunc(components, test.cycles, slices.Equal[[]string]) {
			t.Errorf("Cycles() = %v, %v, want %v", components, err, test.cycles)
		}
		if HasCycle(test.graph) != (len(test.cycles) != 0) {
			t.Errorf("HasCycle() differs from the expected cyclic components %v", test.cycles)
		}
	}
	reversed := func(a, b string) bool { return a > b }
	order, err := Order(map[string][]string{"a": {}, "c": {}, "b": {"a"}}, reversed)
	if err != nil || !slices.Equal(order, []string{"c", "a", "b"}) {
		t.Errorf("Order(reverse) = %v, %v, want [c a b]", order, err)
	}
	sparse := map[string][]string{"a": {"b"}}
	if HasCycle(sparse) {
		t.Error("HasCycle(sparse DAG) = true, want false")
	}
	if _, err := Order(sparse, nil); !errors.Is(err, ErrGraph) {
		t.Errorf("Order(open graph) error = %v, want ErrGraph", err)
	}
	if _, err := Cycles(sparse, nil); !errors.Is(err, ErrGraph) {
		t.Errorf("Cycles(open graph) error = %v, want ErrGraph", err)
	}
}

func TestGraphTraversalSurvivesLongChains(t *testing.T) {
	graph := map[string][]string{}
	for i := range 5000 {
		graph[fmt.Sprintf("n%04d", i)] = []string{fmt.Sprintf("n%04d", i+1)}
	}
	graph["n5000"] = []string{}
	order, err := Order(graph, nil)
	if err != nil || len(order) != 5001 || order[0] != "n5000" || order[5000] != "n0000" {
		t.Errorf("Order(long chain) length = %d, %v, want 5001 dependency-ordered nodes", len(order), err)
	}
	graph["n5000"] = []string{"n0000"}
	components, err := Cycles(graph, nil)
	if err != nil || len(components) != 1 || len(components[0]) != 5001 || !HasCycle(graph) {
		t.Errorf("Cycles(long cycle) count = %d, %v, want one component of 5001 nodes", len(components), err)
	}
}

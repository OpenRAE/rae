package planning

import (
	"fmt"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func dependencyGraph(resources map[string]plannedResource, domain string, refresh bool) map[string][]string {
	result := map[string][]string{}
	for address, resource := range resources {
		if domain == "" || resource.facts.Domain == domain {
			result[address] = []string{}
		}
	}
	for address := range result {
		dependencies := resources[address].facts.OrderingDependencies
		if refresh {
			dependencies = resources[address].facts.RefreshDependencies
		}
		for _, dependency := range dependencies {
			if _, known := result[dependency]; known {
				result[address] = append(result[address], dependency)
			}
		}
	}
	return result
}
func orderingDiagnostics(resources map[string]plannedResource) []diagnostic.Diagnostic {
	result := []diagnostic.Diagnostic{}
	for _, domain := range []string{termProvisioning, termOrchestration, termEvaluation, "participant"} {
		cycles, err := graph.Cycles(dependencyGraph(resources, domain, false), nil)
		if err != nil {
			panic("planning: invalid owned dependency graph")
		}
		for _, cycle := range cycles {
			result = append(result, planDiagnostic(domain+".ordering-cycle", domain, cycle[0], fmt.Sprintf("%s ordering dependencies must be acyclic; detected cycle: %s.", strings.ToUpper(domain[:1])+domain[1:], strings.Join(cycle, ", "))))
		}
	}
	return result
}
func refreshDependents(resources map[string]plannedResource, actions map[string]string) {
	dependencies := dependencyGraph(resources, "", true)
	dependents := map[string][]string{}
	queue, changed := refreshRoots(actions)
	slices.Sort(queue)
	for address, edges := range dependencies {
		for _, dependency := range edges {
			dependents[dependency] = append(dependents[dependency], address)
		}
	}
	for index := 0; index < len(queue); index++ {
		children := dependents[queue[index]]
		slices.Sort(children)
		for _, child := range children {
			if changed[child] {
				continue
			}
			changed[child] = true
			queue = append(queue, child)
			if actions[child] == termUnchanged {
				actions[child] = termUpdate
			}
		}
	}
}

func refreshRoots(actions map[string]string) ([]string, map[string]bool) {
	queue := []string{}
	changed := map[string]bool{}
	for address, action := range actions {
		if action == termCreate || action == termUpdate {
			changed[address] = true
			queue = append(queue, address)
		}
	}
	return queue, changed
}

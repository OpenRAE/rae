package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/graph"

func sdlResourceDimension(v any) error {
	if err := resourceQuantity(v); err != nil {
		return err
	}
	if !nonblankSDLRefs(v, fieldEvidenceRefs) {
		return invalid()
	}
	return resourceDemandQuantity(v, v)
}
func sdlResourcePolicy(v any) error {
	dimensions, owners := object(at(v, "dimensions")), object(at(v, "owners"))
	resources, pools := map[string]bool{}, map[[7]string]bool{}
	edges, children := map[string][]string{}, map[string][]any{}
	for id, dimension := range dimensions {
		owner := owners[stringAt(dimension, "owner_ref")]
		if owner == nil || stringAt(owner, termKind) != termParticipant && stringAt(dimension, "reset") == termEpisode {
			return invalid()
		}
		resources[stringAt(dimension, "resource_kind")] = true
		if err := sdlBudgetPool(dimension, owner, pools); err != nil {
			return err
		}
		if at(dimension, "parent_budget_ref") != nil {
			parent := stringAt(dimension, "parent_budget_ref")
			if err := sdlBudgetParent(dimension, dimensions[parent]); err != nil {
				return err
			}
			edges[id] = []string{parent}
			children[parent] = append(children[parent], at(dimension, "limit"))
		}
	}
	return sdlBudgetGraph(dimensions, resources, edges, children)
}
func sdlBudgetGraph(dimensions map[string]any, resources map[string]bool, edges map[string][]string, children map[string][]any) error {
	if graph.HasCycle(edges) || !subset([]string{termActionRate, termConcurrentActions, termStorageGrowth, termInferenceTokens, termImageGenerations, termAccelerator}, resources) {
		return invalid()
	}
	for parent, limits := range children {
		if !resourceNumbersWithin(at(dimensions[parent], "limit"), limits...) {
			return invalid()
		}
	}
	return nil
}
func sdlBudgetParent(dimension, parent any) error {
	return require(parent != nil && matchingFields(dimension, parent, "resource_kind", "unit", "accounting_mode", "meter_profile_ref") && !numericGreater(at(dimension, "limit"), at(parent, "limit")))
}
func sdlBudgetPool(dimension, owner any, pools map[[7]string]bool) error {
	kind, err := jsonDigest(at(dimension, "resource_kind"))
	if err != nil {
		return err
	}
	key := [7]string{stringAt(dimension, "pool_ref"), stringAt(owner, termKind), stringAt(owner, "ref"), kind, stringAt(dimension, "unit"), stringAt(dimension, "accounting_mode"), stringAt(dimension, "meter_profile_ref")}
	if pools[key] {
		return invalid()
	}
	pools[key] = true
	return nil
}

package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/graph"

func resourcePolicy(v any) error {
	owners, demands := array(at(v, "owners")), array(at(v, "demands"))
	if len(rowSet(owners, "owner_id")) != len(owners) || len(rowSet(demands, "budget_id")) != len(demands) {
		return invalid()
	}
	byOwner, byDemand := map[string]any{}, map[string]any{}
	for _, owner := range owners {
		byOwner[stringAt(owner, "owner_id")] = owner
	}
	for _, demand := range demands {
		byDemand[stringAt(demand, "budget_id")] = demand
	}
	resources, pools, edges := map[string]bool{}, map[string]bool{}, map[string][]string{}
	children := map[string][]any{}
	for _, demand := range demands {
		if err := resourcePolicyDemand(demand, byOwner, byDemand, pools); err != nil {
			return err
		}
		resources[stringAt(demand, "quantity", "resource_kind")] = true
		if at(demand, "parent_budget_ref") != nil {
			parent := stringAt(demand, "parent_budget_ref")
			edges[stringAt(demand, "budget_id")] = []string{parent}
			children[parent] = append(children[parent], at(demand, "limit"))
		}
	}
	if graph.HasCycle(edges) || !subset([]string{termActionRate, termConcurrentActions, termStorageGrowth, termInferenceTokens, termImageGenerations, termAccelerator}, resources) {
		return invalid()
	}
	for parent, limits := range children {
		if !resourceNumbersWithin(at(byDemand[parent], "limit"), limits...) {
			return invalid()
		}
	}
	return nil
}

func resourcePolicyDemand(demand any, owners, demands map[string]any, pools map[string]bool) error {
	owner, quantity := at(demand, "owner"), at(demand, "quantity")
	if !equal(owner, owners[stringAt(owner, "owner_id")]) {
		return invalid()
	}
	if at(demand, "parent_budget_ref") != nil {
		parent := demands[stringAt(demand, "parent_budget_ref")]
		if parent == nil || !matchingFields(quantity, at(parent, "quantity"), "resource_kind", "unit", "accounting_mode", "meter_profile_ref") || numericGreater(at(demand, "limit"), at(parent, "limit")) {
			return invalid()
		}
	}
	key, err := jsonDigest([]any{at(demand, "pool_ref"), at(owner, "kind"), at(owner, "owner_ref"), at(quantity, "resource_kind"), at(quantity, "unit"), at(quantity, "accounting_mode"), at(quantity, "meter_profile_ref")})
	if err != nil || pools[key] {
		return invalid()
	}
	pools[key] = true
	return nil
}

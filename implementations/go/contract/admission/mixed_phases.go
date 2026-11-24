package admission

import "maps"

type mixedUsage struct {
	components, allocations, edges map[string]bool
	allocationPhases, edgePhases   map[string]map[string]bool
}

func mixedPhases(v any) error {
	phases := keySet(at(v, termPhases))
	order := stringsOf(at(v, "phase_order"))
	if len(order) == 0 || !phases[stringAt(v, "initial_phase_id")] || !unique(order) || !equalSet(set(at(v, "phase_order")), phases) || order[0] != stringAt(v, "initial_phase_id") {
		return invalid()
	}
	u := mixedUsage{map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]map[string]bool{}, map[string]map[string]bool{}}
	for id := range object(at(v, termAllocations)) {
		u.allocationPhases[id] = map[string]bool{}
	}
	for id := range object(at(v, termEdges)) {
		u.edgePhases[id] = map[string]bool{}
	}
	for _, phase := range object(at(v, termPhases)) {
		if err := u.phase(v, phase); err != nil {
			return err
		}
	}
	if !equalSet(u.components, keySet(at(v, termComponents))) || !equalSet(u.allocations, keySet(at(v, termAllocations))) || !equalSet(u.edges, keySet(at(v, termEdges))) {
		return invalid()
	}
	for id, actual := range u.allocationPhases {
		if !equalSet(actual, set(at(v, termAllocations, id, "phase_ids"))) {
			return invalid()
		}
	}
	for id, actual := range u.edgePhases {
		if !equalSet(actual, set(at(v, termEdges, id, "phase_ids"))) {
			return invalid()
		}
	}
	return mixedTransitions(v, phases, order)
}
func (u *mixedUsage) phase(v, phase any) error {
	if !fieldsUnique(phase, "active_component_ids", "active_allocation_ids", "active_edge_ids") || !mixedEvidenceUnique(phase) {
		return invalid()
	}
	components, allocations, edges := set(at(phase, "active_component_ids")), set(at(phase, "active_allocation_ids")), set(at(phase, "active_edge_ids"))
	if !subsetSet(components, keySet(at(v, termComponents))) || !subsetSet(allocations, keySet(at(v, termAllocations))) || !subsetSet(edges, keySet(at(v, termEdges))) {
		return invalid()
	}
	maps.Copy(u.components, components)
	maps.Copy(u.allocations, allocations)
	maps.Copy(u.edges, edges)
	providers := map[string]string{}
	phaseID := stringAt(phase, "phase_id")
	for id := range allocations {
		allocation := at(v, termAllocations, id)
		u.allocationPhases[id][phaseID] = true
		provider := stringAt(allocation, "provider_component_id")
		if !components[provider] {
			return invalid()
		}
		key := join(stringAt(allocation, termTargetKind), stringAt(allocation, "target_address"))
		if incumbent, ok := providers[key]; ok && incumbent != provider {
			return invalid()
		}
		providers[key] = provider
	}
	for id := range edges {
		edge := at(v, termEdges, id)
		u.edgePhases[id][phaseID] = true
		if !components[stringAt(edge, "source_component_id")] || !components[stringAt(edge, "target_component_id")] {
			return invalid()
		}
	}
	return nil
}
func mixedTransitions(v any, phases map[string]bool, order []string) error {
	actual, expected := map[string]bool{}, map[string]bool{}
	for index := 1; index < len(order); index++ {
		expected[join(order[index-1], order[index])] = true
	}
	for _, transition := range object(at(v, termTransitions)) {
		source, target := stringAt(transition, "source_phase_id"), stringAt(transition, "target_phase_id")
		key := join(source, target)
		if !phases[source] || !phases[target] || actual[key] {
			return invalid()
		}
		actual[key] = true
	}
	return require(equalSet(actual, expected))
}

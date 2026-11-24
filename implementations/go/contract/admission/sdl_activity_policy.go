package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/graph"

func sdlActivityPolicy(v any) error {
	if !nonblankSDLRefs(v, "work_window_refs", "pause_window_refs") {
		return invalid()
	}
	candidates := object(at(v, "action_candidates"))
	edges := map[string][]string{}
	for name, candidate := range candidates {
		for _, ref := range stringsOf(at(candidate, "depends_on")) {
			if candidates[ref] == nil {
				return invalid()
			}
			edges[name] = append(edges[name], ref)
		}
	}
	if graph.HasCycle(edges) {
		return invalid()
	}
	if err := sdlOptionalInterval(v, "max_occurrences", "max_action_attempts"); err != nil {
		return err
	}
	return sdlOptionalInterval(v, "max_burst_size", "max_occurrences")
}
func sdlResourceActivityPolicy(v any) error {
	if err := sdlActivityPolicy(v); err != nil {
		return err
	}
	budget := at(v, "resource_budget")
	var concurrency any
	count := 0
	for _, dimension := range object(at(budget, "dimensions")) {
		owner := at(budget, "owners", stringAt(dimension, "owner_ref"))
		if stringAt(dimension, "resource_kind") == termConcurrentActions && stringAt(owner, termKind) == termParticipant {
			concurrency = at(dimension, "limit")
			count++
		}
	}
	maximum := defaultMember(v, "max_in_flight", jsonOne)
	_, concrete := number(maximum)
	return require(count == 1 && (!concrete || numericEqual(maximum, concurrency)))
}

package admission

func (r *mixedResolution) trial(v any) error {
	id := stringAt(v, termProfileID)
	for component := range object(at(v, termComponents)) {
		if !r.snapshot.ProjectionMembership[[2]string{id, component}] {
			return invalid()
		}
	}
	effects := map[string]map[string]bool{}
	for allocation := range object(at(v, termAllocations)) {
		resolved := r.snapshot.AllocationEffects[[2]string{id, allocation}]
		if len(resolved) == 0 || !flowUniqueReferences(resolved) {
			return invalid()
		}
		effects[allocation] = set(jsonStrings(resolved))
	}
	for _, phase := range object(at(v, termPhases)) {
		if err := mixedActiveEffectOverlap(v, phase, effects); err != nil {
			return err
		}
	}
	_, known := r.snapshot.ResourceRefs[id]
	return require(known)
}

func mixedActiveEffectOverlap(v, phase any, effects map[string]map[string]bool) error {
	active := stringsOf(at(phase, "active_allocation_ids"))
	for index, left := range active {
		for _, right := range active[index+1:] {
			if equal(at(v, termAllocations, left, "provider_component_id"), at(v, termAllocations, right, "provider_component_id")) {
				continue
			}
			if !disjoint(boolKeys(effects[left]), effects[right]) {
				return invalid()
			}
		}
	}
	return nil
}

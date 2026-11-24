package admission

func (r *mixedResolution) backendBindings(profile any, edges, handoffs map[string]any) error {
	active := map[string]bool{}
	for _, phase := range object(at(profile, termPhases)) {
		for _, id := range stringsOf(at(phase, "active_edge_ids")) {
			active[id] = true
		}
	}
	for id := range active {
		if err := mixedBackendEdge(profile, at(profile, termEdges, id), edges[id]); err != nil {
			return err
		}
		delete(edges, id)
	}
	for id, transition := range object(at(profile, termTransitions)) {
		if err := r.backendHandoff(profile, transition, handoffs[id]); err != nil {
			return err
		}
		delete(handoffs, id)
	}
	return require(len(edges) == 0 && len(handoffs) == 0)
}

func mixedBackendEdge(profile, edge, installed any) error {
	ordering := stringAt(edge, "time_binding", "ordering_basis")
	if installed == nil || ordering == termWallClockOnly || ordering == statusUnknown || ordering == statusUnsupported {
		return invalid()
	}
	allocation := at(profile, termAllocations, stringAt(installed, "owner_allocation_id"))
	if allocation == nil || stringAt(allocation, "target_kind") != "action-family" || !equal(at(allocation, "provider_component_id"), at(edge, "target_component_id")) || !equal(at(allocation, "target_address"), at(installed, "destination_action_address")) || disjoint(stringsOf(at(allocation, "phase_ids")), set(at(edge, "phase_ids"))) {
		return invalid()
	}
	if !equal(at(installed, "owner_component_id"), at(edge, "target_component_id")) || !equal(at(installed, "participant_address"), at(edge, "crossing_subject", "participant_address")) || !equal(at(installed, "audience_scope_ref"), at(edge, "audience_scope_ref")) || !equal(at(installed, "bridge", "service_ref"), at(edge, "routing_ref")) || !equal(at(installed, "mapping_loss"), at(edge, "mapping_loss")) || !equalSet(set(at(installed, "required_evidence_refs")), rowSet(at(edge, "evidence_bindings"), "evidence_ref")) {
		return invalid()
	}
	actual, admitted := at(installed, "time"), at(edge, "time_binding")
	return require(matchingFields(actual, admitted, "time_model_ref", "time_model_digest", "source_clock_address", "ordering_basis", "temporal_coupling") && equal(at(actual, "destination_clock_address"), at(admitted, "target_clock_address")) && equal(at(actual, "mapping_ref"), at(admitted, "mapping_address")))
}

func (r *mixedResolution) backendHandoff(profile, transition, installed any) error {
	source, target := set(at(profile, termPhases, stringAt(transition, "source_phase_id"), "active_component_ids")), set(at(profile, termPhases, stringAt(transition, "target_phase_id"), "active_component_ids"))
	if equalSet(source, target) {
		return require(installed == nil)
	}
	leaving, joining := mixedSetDifference(source, target), mixedSetDifference(target, source)
	if len(leaving) != 1 || len(joining) != 1 || installed == nil {
		return invalid()
	}
	if stringAt(installed, "source_component_id") != leaving[0] || stringAt(installed, "destination_component_id") != joining[0] || !equal(at(installed, "source_owner_ref"), at(profile, termComponents, leaving[0], "native_ownership_ref")) || !equal(at(installed, "destination_owner_ref"), at(profile, termComponents, joining[0], "native_ownership_ref")) || !equalSet(set(at(installed, "required_evidence_refs")), rowSet(at(transition, "evidence_bindings"), "evidence_ref")) {
		return invalid()
	}
	time := at(installed, "time")
	return r.time(stringAt(time, "time_model_ref"), stringAt(time, "time_model_digest"), stringAt(time, "source_clock_address"), stringAt(time, "destination_clock_address"), stringAt(time, "mapping_ref"))
}

func mixedSetDifference(a, b map[string]bool) []string {
	result := []string{}
	for key := range a {
		if !b[key] {
			result = append(result, key)
		}
	}
	return result
}

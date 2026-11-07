package admission

func (r *mixedResolution) profile(v any) error {
	id := stringAt(v, termProfileID)
	scenario := at(v, "scenario_snapshot_ref")
	if !equal(r.scenarios[stringAt(scenario, "ref_id")], scenario) {
		return invalid()
	}
	checks := []struct {
		field string
		check func(string, any) error
	}{
		{termComponents, r.component}, {termAllocations, r.allocation}, {termEdges, r.edge}, {termTransitions, r.transition},
	}
	for _, entry := range checks {
		for _, record := range object(at(v, entry.field)) {
			if err := entry.check(id, record); err != nil {
				return err
			}
		}
	}
	for _, field := range []string{termPhases, termTransitions} {
		for _, carrier := range object(at(v, field)) {
			if err := r.evidence(id, carrier); err != nil {
				return err
			}
		}
	}
	return nil
}

func (r *mixedResolution) component(id string, v any) error {
	if err := r.charge(); err != nil {
		return err
	}
	trusted := r.components[[2]string{id, stringAt(v, termComponentID)}]
	return require(trusted != nil && matchingFields(v, trusted, termComponentID, "apparatus_identity_ref", "manifest_ref", "realization_envelope", "native_ownership_ref"))
}

func (r *mixedResolution) allocation(id string, v any) error {
	if err := r.charge(); err != nil {
		return err
	}
	trusted := r.allocations[[2]string{id, stringAt(v, "allocation_id")}]
	if trusted == nil || r.snapshot.CompiledTargets[stringAt(v, "target_address")] != stringAt(v, "target_kind") || !matchingFields(v, trusted, "allocation_id", "target_kind", "target_address", "provider_component_id", "participant_identity_ref", "controller_ref", "action_authority_ref", "routing_ref") {
		return invalid()
	}
	for _, requirement := range array(at(v, "feature_requirements")) {
		if err := r.feature(id, stringAt(v, "provider_component_id"), requirement); err != nil {
			return err
		}
	}
	return nil
}

func (r *mixedResolution) feature(id, component string, v any) error {
	if err := r.charge(); err != nil {
		return err
	}
	if at(v, "downgrade_policy_ref") != nil {
		expected := MixedFeatureDowngrade{ProfileID: id, ComponentID: component, Feature: stringAt(v, "feature"), RequiredLevel: stringAt(v, "required_level"), AllowedLevel: stringAt(v, "allowed_downgrade_level"), PolicyRef: stringAt(v, "downgrade_policy_ref"), ProvenanceRef: stringAt(v, "downgrade_provenance_ref")}
		found := false
		for _, grant := range r.snapshot.FeatureDowngrades {
			found = found || grant == expected
		}
		if !found {
			return invalid()
		}
	}
	if err := r.context.ResolveMixedFeature(id, component, controlRaw(v)); err != nil {
		return invalid()
	}
	return nil
}

func (r *mixedResolution) evidence(id string, v any) error {
	for _, binding := range array(at(v, "evidence_bindings")) {
		if err := r.charge(); err != nil {
			return err
		}
		accepted := r.snapshot.EvidenceSatisfaction[[2]string{id, stringAt(binding, "obligation_ref")}]
		if !flowUniqueReferences(accepted) || !set(jsonStrings(accepted))[stringAt(binding, "evidence_ref")] {
			return invalid()
		}
	}
	return nil
}

func (r *mixedResolution) edge(id string, v any) error {
	if err := r.charge(); err != nil {
		return err
	}
	trusted := r.edges[[2]string{id, stringAt(v, "edge_id")}]
	if trusted == nil || !matchingFields(v, trusted, "edge_id", "source_component_id", "target_component_id", "crossing_scope_address", "crossing_subject", "audience_scope_ref", "policy", "controller_ref", "authority_ref", "routing_ref", "disclosure_authority_ref", "native_ownership_ref", "time_binding", "mapping_loss", "failure_behavior") {
		return invalid()
	}
	if err := r.evidence(id, v); err != nil {
		return err
	}
	time := at(v, "time_binding")
	return r.time(stringAt(time, "time_model_ref"), stringAt(time, "time_model_digest"), stringAt(time, "source_clock_address"), stringAt(time, "target_clock_address"), stringAt(time, "mapping_address"))
}

func (r *mixedResolution) time(ref, digest, source, target, mapping string) error {
	model := r.times[ref]
	sourceClock, targetClock, relation := at(model, "clocks", source), at(model, "clocks", target), at(model, "mappings", mapping)
	return require(model != nil && r.snapshot.TimeModelDigests[ref] == digest && sourceClock != nil && targetClock != nil && relation != nil && equal(at(relation, "source_domain_address"), at(sourceClock, "time_domain_address")) && equal(at(relation, "target_domain_address"), at(targetClock, "time_domain_address")))
}

func (r *mixedResolution) transition(id string, v any) error {
	if err := r.charge(); err != nil {
		return err
	}
	trusted := r.transitions[[2]string{id, stringAt(v, "transition_id")}]
	return require(trusted != nil && matchingFields(v, trusted, "transition_id", "source_phase_id", "target_phase_id", "trigger_ref", "evaluator_ref"))
}

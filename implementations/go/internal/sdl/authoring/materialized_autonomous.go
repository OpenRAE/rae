package authoring

type autonomousChecks struct {
	root         materializedChecks
	name         string
	spec, policy map[string]any
	participants map[string]bool
	roles        map[string]string
}

func (c materializedChecks) autonomous() error {
	roles := c.participantRoles()
	owners := map[string]bool{}
	for name, raw := range object(c.value[behaviorSection]) {
		spec := object(raw)
		policy := object(spec["autonomous_execution"])
		if policy == nil {
			continue
		}
		selected := selectedParticipants(spec, object(c.value[agentsSection]), roles)

		if err := claimAutonomousParticipants(selected, owners); err != nil {
			return err
		}
		check := autonomousChecks{root: c, name: name, spec: spec, policy: policy, participants: selected, roles: roles}
		if err := check.references(); err != nil {
			return err
		}
		if err := check.time(); err != nil {
			return err
		}
		if err := check.resourceOwners(); err != nil {
			return err
		}
		if err := check.evaluation(); err != nil {
			return err
		}
	}
	return nil
}
func (a autonomousChecks) references() error {
	if len(array(a.spec[participantRefsField])) == 0 {
		return semanticInvalid()
	}
	features := stringSet(array(a.spec[backendFeaturesField]))
	for _, required := range []string{actionsSection, "autonomous_execution", "behavior_history", boundariesSection, "temporal_contracts"} {
		if !features[required] {
			return semanticInvalid()
		}
	}
	actions := array(a.policy["action_order"])
	if candidates := object(a.policy["action_candidates"]); candidates != nil {
		actions = []any{}
		for _, raw := range candidates {
			actions = append(actions, object(raw)["action_ref"])
		}
	}
	if err := a.binding(actions, actionRefsField, "actions"); err != nil {
		return err
	}
	return a.binding([]any{a.policy["observation_boundary_ref"]}, boundaryRefsField, boundariesSection)
}
func (a autonomousChecks) binding(refs []any, parentField, agentField string) error {
	parent := stringSet(array(a.spec[parentField]))
	for _, ref := range concreteRefs(refs) {
		if !parent[ref] || !a.root.participantsPermit(a.participants, agentField, ref) {
			return semanticInvalid()
		}
	}
	return nil
}
func (a autonomousChecks) evaluation() error {
	authority := object(a.policy["evaluation_authority"])
	switch authority["mode"] {
	case "none":
		return a.nonEvaluated()
	case "declared":
		for _, ref := range concreteRefs(array(authority["objective_refs"])) {
			name, ok := sectionRef(ref, objectivesSection, object(a.root.value[objectivesSection]))
			assignment := object(object(a.root.value[objectivesSection])[name])["assigned_participant"]
			if !ok || !variable(assignment) && !a.participants[text(assignment)] {
				return semanticInvalid()
			}
		}
		for _, field := range []string{"proof_producer_refs", "score_authority_refs", "receipt_authority_refs"} {
			if len(concreteRefs(array(authority[field]))) > 0 {
				return semanticInvalid()
			}
		}
	}
	return nil
}
func (a autonomousChecks) nonEvaluated() error {
	if len(array(a.spec[outcomeRefsField])) > 0 || len(array(a.spec[authorityScopeRefsField])) > 0 {
		return semanticInvalid()
	}
	for name := range a.participants {
		if a.roles[name] != "green" {
			return semanticInvalid()
		}
		for _, raw := range object(a.root.value[objectivesSection]) {
			if object(raw)["assigned_participant"] == name {
				return semanticInvalid()
			}
		}
	}
	return nil
}

func claimAutonomousParticipants(selected, owners map[string]bool) error {
	for name := range selected {
		if owners[name] {
			return semanticInvalid()
		}
		owners[name] = true
	}
	return nil
}

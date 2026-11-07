package authoring

func (c materializedChecks) participantBehavior() error {
	roles := c.participantRoles()
	for _, raw := range object(c.value[boundariesSection]) {
		if err := boundaryVisibility(object(raw)); err != nil {
			return err
		}
	}
	for _, raw := range object(c.value[actionsSection]) {
		if err := c.interactions(object(raw)); err != nil {
			return err
		}
	}
	for name, raw := range object(c.value[behaviorSection]) {
		spec := object(raw)
		if err := c.behaviorReferences(spec, roles); err != nil {
			return err
		}
		if err := c.behaviorVocabulary(spec); err != nil {
			return err
		}
		if err := c.toolAffordances(name, spec, roles); err != nil {
			return err
		}
	}
	return nil
}
func (c materializedChecks) participantRoles() map[string]string {
	entities := map[string]any{}
	collectEntities(object(c.value[entitiesField]), "", entities)
	result := map[string]string{}
	for name, raw := range object(c.value[agentsSection]) {
		agent := object(raw)
		role := text(agent[roleTerm])
		affiliations := array(agent["affiliations"])
		if role == "" && len(affiliations) == 1 {
			if variable(affiliations[0]) {
				role = text(affiliations[0])
			} else {
				role = text(object(entities[text(affiliations[0])])[roleTerm])
			}
		}
		if role != "" {
			result[name] = role
		}
	}
	return result
}
func (c materializedChecks) behaviorReferences(spec map[string]any, roles map[string]string) error {
	for field, section := range map[string]string{participantRefsField: agentsSection, actionRefsField: actionsSection, boundaryRefsField: boundariesSection, outcomeRefsField: outcomeRulesSection} {
		if err := referencesPresent(array(spec[field]), object(c.value[section])); err != nil {
			return err
		}
	}
	if err := behaviorRoleRefs(array(spec[participantRoleRefsField]), roles, true); err != nil {
		return err
	}
	for _, ref := range concreteRefs(array(spec[authorityScopeRefsField])) {
		target, ok := c.index.resolveTarget(ref, nil)
		if !ok || !target.authority {
			return semanticInvalid()
		}
	}
	return nil
}
func behaviorRoleRefs(refs []any, roles map[string]string, allowUnresolved bool) error {
	known := map[string]any{}
	for _, role := range roles {
		if allowUnresolved && variable(role) {
			return nil
		}
		known[role] = true
	}
	return referencesPresent(refs, known)
}
func (c materializedChecks) behaviorVocabulary(spec map[string]any) error {
	if mode := text(spec["behavior_mode"]); mode != "" {
		if err := c.parser.authority.CheckScope("behavior_specifications.behavior_mode", mode); err != nil {
			return err
		}
	}
	for _, ref := range concreteRefs(array(spec[backendFeaturesField])) {
		if !c.parser.authority.Permits("participant-runtime-behavior-features", ref) && !c.parser.authority.Permits("participant-runtime-interaction-features", ref) {
			return semanticInvalid()
		}
	}
	for _, ref := range concreteRefs(array(spec[evidenceContractsField])) {
		if !c.parser.evidenceContracts[ref] {
			return semanticInvalid()
		}
	}
	return nil
}
func selectedParticipants(selector map[string]any, agents map[string]any, roles map[string]string) map[string]bool {
	result, selectedRoles := map[string]bool{}, stringSet(array(selector[participantRoleRefsField]))
	for _, ref := range array(selector[participantRefsField]) {
		if agents[text(ref)] != nil {
			result[text(ref)] = true
		}
	}
	for name, role := range roles {
		if selectedRoles[role] {
			result[name] = true
		}
	}
	return result
}
func stringSet(refs []any) map[string]bool {
	result := map[string]bool{}
	for _, ref := range refs {
		result[text(ref)] = true
	}
	return result
}
func (c materializedChecks) interactions(action map[string]any) error {
	for _, raw := range array(action["interactions"]) {
		interaction := object(raw)
		if err := referencesPresent(array(interaction["related_actions"]), object(c.value[actionsSection])); err != nil {
			return err
		}
		for _, ref := range concreteRefs([]any{interaction[targetField]}) {
			if !c.index.actionTarget(ref) {
				return semanticInvalid()
			}
		}
		for _, ref := range concreteRefs(array(interaction["shared_state_refs"])) {
			target, ok := c.index.resolveTarget(ref, nil)
			if !ok || !target.action || target.kind == agentsSection || target.kind == entitiesField {
				return semanticInvalid()
			}
		}
	}
	return nil
}

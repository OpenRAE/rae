package authoring

func (c materializedChecks) evidence() error {
	for _, raw := range object(c.value["evidence_requirements"]) {
		if err := c.evidenceRequirement(object(raw)); err != nil {
			return err
		}
	}
	return c.forwardingEvidenceRoles()
}

func (c materializedChecks) evidenceRequirement(requirement map[string]any) error {
	for _, field := range []string{"source_refs", scopeRefsField, "channel_refs"} {
		if err := c.index.targetReferences(array(requirement[field])); err != nil {
			return err
		}
	}
	for _, field := range []string{"trigger_ref", "boundary_ref"} {
		if ref := text(requirement[field]); ref != "" {
			if err := c.index.targetReferences([]any{ref}); err != nil {
				return err
			}
		}
	}
	return c.observationDemand(object(requirement["observation_demand"]))
}

func (c materializedChecks) observationDemand(demand map[string]any) error {
	if demand == nil {
		return nil
	}
	if _, err := c.scopes.resolve(text(demand["scope"])); err != nil {
		return err
	}
	selector := object(demand["selector"])
	if selector == nil {
		return nil
	}
	pointers := append([]any{selector["semantic_scope"]}, array(selector["excluded_scopes"])...)
	for _, pointer := range pointers {
		if _, err := c.scopes.resolve(text(pointer)); err != nil {
			return err
		}
	}
	return c.index.targetReferences(array(selector["component_refs"]))
}

func (c materializedChecks) forwardingEvidenceRoles() error {
	bound := c.apparatusBindings()
	for address := range c.index.addresses {
		entry := c.index.aliases[address][address]
		if entry.kind != forwardingSection {
			continue
		}
		role := text(entry.value["ownership_role"])
		if role == "" {
			role = "system_under_test"
		}
		if role == "measurement_apparatus" && !bound[address] || role == "system_under_test" && bound[address] {
			return semanticInvalid()
		}
	}
	return nil
}

func (c materializedChecks) apparatusBindings() map[string]bool {
	bound := map[string]bool{}
	for _, raw := range object(c.value["evidence_requirements"]) {
		requirement := object(raw)
		if text(requirement["source_class"]) != "apparatus" {
			continue
		}
		for _, reference := range array(requirement["source_refs"]) {
			for address, entry := range c.index.aliases[text(reference)] {
				if entry.kind == forwardingSection {
					bound[address] = true
				}
			}
		}
	}
	return bound
}

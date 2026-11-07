package authoring

func (c materializedChecks) agents() error {
	entities := map[string]any{}
	collectEntities(object(c.value[entitiesField]), "", entities)
	services := map[string]bool{}
	for _, raw := range object(c.value[nodesSection]) {
		for name := range runtimeIDs(raw, "services.*.name") {
			services[name] = true
		}
	}
	scopes := operatingScopeIndex(c.value)
	for _, raw := range object(c.value[agentsSection]) {
		agent := object(raw)
		if err := c.agentReferences(agent, entities, scopes); err != nil {
			return err
		}
		if err := c.agentKnowledge(object(agent["initial_knowledge"]), services); err != nil {
			return err
		}
	}
	return nil
}

func (c materializedChecks) agentReferences(agent, entities map[string]any, scopes *declarationIndex) error {
	if err := referencesPresent(array(agent["affiliations"]), entities); err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, raw := range array(agent["affiliations"]) {
		if variable(raw) {
			continue
		}
		ref := text(raw)
		if seen[ref] {
			return semanticInvalid()
		}
		seen[ref] = true
	}
	for field, section := range map[string]string{"starting_accounts": accountsSection, boundariesSection: boundariesSection} {
		if err := referencesPresent(array(agent[field]), object(c.value[section])); err != nil {
			return err
		}
	}
	if contracts := object(c.value[actionsSection]); len(contracts) > 0 {
		if err := referencesPresent(array(agent["actions"]), contracts); err != nil {
			return err
		}
	}
	if err := c.agentSubnets(array(agent["allowed_subnets"])); err != nil {
		return err
	}
	return c.agentAuthorityAndScope(agent, scopes)
}

func (c materializedChecks) agentAuthorityAndScope(agent map[string]any, scopes *declarationIndex) error {
	for _, ref := range array(agent["authority_anchors"]) {
		if !variable(ref) && !c.index.uniqueDeclared(text(ref)) {
			return semanticInvalid()
		}
	}
	for _, ref := range array(agent["operating_scope"]) {
		if variable(ref) {
			continue
		}
		if _, ok := scopes.resolveTarget(text(ref), nil); !ok {
			return semanticInvalid()
		}
	}
	return nil
}

func (c materializedChecks) agentKnowledge(knowledge map[string]any, services map[string]bool) error {
	for _, ref := range array(knowledge["hosts"]) {
		if !variable(ref) {
			if err := c.computeTarget(text(ref)); err != nil {
				return err
			}
		}
	}
	if err := c.agentSubnets(array(knowledge["subnets"])); err != nil {
		return err
	}
	if err := referencesPresent(array(knowledge[accountsSection]), object(c.value[accountsSection])); err != nil {
		return err
	}
	return runtimeReferences(array(knowledge[servicesField]), services)
}

func (c materializedChecks) agentSubnets(references []any) error {
	if err := referencesPresent(references, object(c.value[infrastructureField])); err != nil {
		return err
	}
	for _, ref := range references {
		if !variable(ref) && object(object(c.value[nodesSection])[text(ref)])["type"] != switchType {
			return semanticInvalid()
		}
	}
	return nil
}

func operatingScopeIndex(value map[string]any) *declarationIndex {
	index := &declarationIndex{aliases: map[string]map[string]declaration{}, addresses: map[string]bool{}}
	category := declaration{target: true}
	for name, raw := range object(value[nodesSection]) {
		node := object(raw)
		if node["type"] == computeType {
			index.add(nodesPrefix+name, name, category)
		}
		if node["type"] == switchType && object(value[infrastructureField])[name] != nil {
			index.add("infrastructure."+name, name, category)
		}
		index.namedItems(array(node[servicesField]), nodesPrefix+name+".services.", true, servicesField)
	}
	for name, raw := range object(value[contentField]) {
		index.add("content."+name, name, category)
		index.namedItems(array(object(raw)["items"]), "content."+name+".items.", true, "content-item")
	}
	return index
}

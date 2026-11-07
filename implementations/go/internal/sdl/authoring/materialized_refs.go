package authoring

func (c materializedChecks) computeTarget(reference string) error {
	node, present := object(c.value[nodesSection])[reference]
	if !present || object(node)["type"] != computeType {
		return semanticInvalid()
	}
	return nil
}
func (c materializedChecks) contentAndAccounts() error {
	for _, raw := range object(c.value[contentField]) {
		if err := c.computeTarget(text(object(raw)[targetField])); err != nil {
			return err
		}
	}
	for _, raw := range object(c.value[accountsSection]) {
		account := object(raw)
		if err := c.computeTarget(text(account["node"])); err != nil {
			return err
		}
		if err := credentialBindings(account); err != nil {
			return err
		}
	}
	return nil
}
func credentialBindings(account map[string]any) error {
	bindings := array(account["credential_bindings"])
	if len(bindings) == 0 {
		return nil
	}
	identities, pairs := map[string]bool{}, map[[2]string]bool{}
	primary := []map[string]any{}
	for _, raw := range bindings {
		binding := object(raw)
		identity := text(binding["credential_id"])
		pair := [2]string{text(binding["purpose"]), text(binding["auth_method"])}
		if identities[identity] || pairs[pair] {
			return semanticInvalid()
		}
		identities[identity], pairs[pair] = true, true
		if pair[0] == "primary_authentication" {
			primary = append(primary, binding)
		}
	}
	if len(primary) != 1 {
		return semanticInvalid()
	}
	method := "password"
	if supplied, present := account["auth_method"]; present {
		method = text(supplied)
	}
	if primary[0]["auth_method"] != method {
		return semanticInvalid()
	}
	return nil
}
func (c materializedChecks) propositions() error {
	index := c.index
	for _, raw := range object(c.value[propositionsField]) {
		if err := c.propositionReferences(object(raw), index); err != nil {
			return err
		}
	}
	for _, raw := range object(c.value[assertionsSection]) {
		if err := referencesPresent([]any{object(raw)["proposition"]}, object(c.value[propositionsField])); err != nil {
			return err
		}
	}
	for _, raw := range object(c.value[conditionsSection]) {
		if reference := text(object(raw)["proposition"]); reference != "" {
			if err := referencesPresent([]any{reference}, object(c.value[propositionsField])); err != nil {
				return err
			}
		}
	}
	return c.assertionUses()
}
func (c materializedChecks) assertionRole(references []any, allowed ...string) error {
	assertions := object(c.value[assertionsSection])
	if err := referencesPresent(references, assertions); err != nil {
		return err
	}
	for _, raw := range references {
		role := text(object(assertions[text(raw)])[roleTerm])
		found := false
		for _, accepted := range allowed {
			found = found || accepted == role
		}
		if !found {
			return semanticInvalid()
		}
	}
	return nil
}
func (c materializedChecks) assertionUses() error {
	for _, raw := range object(c.value[objectivesSection]) {
		if err := c.assertionRole(array(object(object(raw)["success"])[assertionsSection]), "invariant", "postcondition"); err != nil {
			return err
		}
	}
	for _, raw := range object(c.value[eventsSection]) {
		if err := c.assertionRole(array(object(raw)[assertionsSection]), "precondition"); err != nil {
			return err
		}
	}
	for _, raw := range object(c.value[agentsSection]) {
		if err := c.assertionRole(array(object(raw)["starting_assertions"]), "precondition"); err != nil {
			return err
		}
	}
	return nil
}

func (c materializedChecks) propositionReferences(proposition map[string]any, index *declarationIndex) error {
	for _, reference := range array(proposition["subjects"]) {
		candidates := index.aliases[text(reference)]
		count := 0
		for _, candidate := range candidates {
			if candidate.target {
				count++
			}
		}
		if count != 1 {
			return semanticInvalid()
		}
	}
	if err := referencesPresent(array(proposition["evidence_requirements"]), object(c.value["evidence_requirements"])); err != nil {
		return err
	}
	return nil
}

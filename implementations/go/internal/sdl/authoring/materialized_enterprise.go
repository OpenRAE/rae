package authoring

const (
	directoryFederatesType = "directory_federates_to"
	domainControllerType   = "domain_controller_for"
	joinsDomainType        = "joins_domain"
	forestTrustsType       = "forest_trusts"
)

func (c materializedChecks) enterpriseIdentity() error {
	if err := c.forestMembership(); err != nil {
		return err
	}
	for _, facade := range object(c.value[identityFacadesField]) {
		service := text(object(facade)["service_ref"])
		if !variable(service) && len(c.serviceOwners[service]) == 0 {
			return semanticInvalid()
		}
	}
	return c.enterpriseRelationships()
}

func (c materializedChecks) enterpriseRelationships() error {
	trusts := map[[2]string]bool{}
	federations := map[string]bool{}
	for _, raw := range object(c.value[relationshipsField]) {
		relationship := object(raw)
		if err := relationshipDetail(relationship, map[string]string{forestTrustsType: forestTrustField, directoryFederatesType: identityFederationField}); err != nil {
			return err
		}
		if variable(relationship["type"]) || variable(relationship[sourceField]) || variable(relationship[targetField]) {
			continue
		}
		switch text(relationship["type"]) {
		case forestTrustsType:
			if err := c.forestTrust(relationship, trusts); err != nil {
				return err
			}
		case directoryFederatesType:
			if err := c.identityFederation(relationship, federations); err != nil {
				return err
			}
		}
	}
	return nil
}

func (c materializedChecks) forestMembership() error {
	domains := object(c.value[identityDomainsField])
	forests := object(c.value[identityForestsField])
	membership := map[string]int{}
	for _, raw := range forests {
		forest := object(raw)
		if err := forestMembers(forest, domains, membership); err != nil {
			return err
		}
	}
	if len(forests) > 0 {
		for domain := range domains {
			if membership[domain] != 1 {
				return semanticInvalid()
			}
		}
	}
	return nil
}

func forestMembers(forest, domains map[string]any, membership map[string]int) error {
	members := map[string]bool{}
	for _, reference := range array(forest["domain_refs"]) {
		if variable(reference) {
			continue
		}
		domain, ok := sectionRef(text(reference), identityDomainsField, domains)
		if !ok {
			return semanticInvalid()
		}
		members[domain] = true
		membership[domain]++
	}
	root := text(forest["root_domain_ref"])
	if !variable(root) {
		domain, ok := sectionRef(root, identityDomainsField, domains)
		if !ok || !members[domain] {
			return semanticInvalid()
		}
	}
	return nil
}

func (c materializedChecks) forestTrust(relationship map[string]any, seen map[[2]string]bool) error {
	forests := object(c.value[identityForestsField])
	source, sourceOK := sectionRef(text(relationship[sourceField]), identityForestsField, forests)
	target, targetOK := sectionRef(text(relationship[targetField]), identityForestsField, forests)
	if !sourceOK || !targetOK || source == target {
		return semanticInvalid()
	}
	if source > target {
		source, target = target, source
	}
	pair := [2]string{source, target}
	if seen[pair] {
		return semanticInvalid()
	}
	seen[pair] = true
	return nil
}

func (c materializedChecks) identityFederation(relationship map[string]any, seen map[string]bool) error {
	source := text(relationship[sourceField])
	_, domainOK := sectionRef(source, identityDomainsField, object(c.value[identityDomainsField]))
	_, forestOK := sectionRef(source, identityForestsField, object(c.value[identityForestsField]))
	target, targetOK := sectionRef(text(relationship[targetField]), identityFacadesField, object(c.value[identityFacadesField]))
	if !domainOK && !forestOK || !targetOK || seen[target] {
		return semanticInvalid()
	}
	seen[target] = true
	return nil
}

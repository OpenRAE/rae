package authoring

import "strings"

type endpointKinds [2][]string

func relationshipKinds() map[string]endpointKinds {
	return map[string]endpointKinds{
		domainControllerType:   {{nodesSection}, {identityDomainsField}},
		joinsDomainType:        {{nodesSection}, {identityDomainsField}},
		forestTrustsType:       {{identityForestsField}, {identityForestsField}},
		directoryFederatesType: {{identityDomainsField, identityForestsField}, {identityFacadesField}},
		placedOnCarrierType:    {{nodesSection}, {nodesSection}},
		usesSharedServiceType:  {{deploymentTenantsField}, {servicesField}},
		participantField:       {{agentsSection}, {agentsSection}},
		databaseAccessField:    {{applicationsField}, {databaseServicesField, "database_services.databases"}},
		mailAccessField:        {nil, {"mail_services.*"}},
	}
}

func (c materializedChecks) relationships() error {
	kinds := relationshipKinds()
	bindings := map[string]string{"domain_controller": domainControllerType, "domain_join": joinsDomainType, forestTrustField: forestTrustsType, identityFederationField: directoryFederatesType, "carrier_placement": placedOnCarrierType, sharedServiceField: usesSharedServiceType, participantField: participantField, databaseAccessField: databaseAccessField, mailAccessField: mailAccessField}
	for _, raw := range object(c.value[relationshipsField]) {
		relationship := object(raw)
		if err := c.relationshipBindings(relationship, kinds, bindings); err != nil {
			return err
		}
		for _, check := range []func(map[string]any) error{c.relationshipDatabase, c.relationshipMail, c.relationshipForwarding, c.relationshipIntegration, c.relationshipProxy} {
			if err := check(relationship); err != nil {
				return err
			}
		}
	}
	return nil
}

func (c materializedChecks) relationshipBindings(relationship map[string]any, kinds map[string]endpointKinds, bindings map[string]string) error {
	if err := c.relationshipEndpoints(relationship, kinds[text(relationship["type"])]); err != nil {
		return err
	}
	for field, kind := range bindings {
		if relationship[field] != nil {
			if err := c.relationshipEndpoints(relationship, kinds[kind]); err != nil {
				return err
			}
		}
	}
	return nil
}

func (c materializedChecks) relationshipEndpoints(relationship map[string]any, kinds endpointKinds) error {
	for position, side := range []string{sourceField, targetField} {
		reference := text(relationship[side])
		if variable(reference) {
			continue
		}
		_, ok := c.index.resolveTarget(reference, kinds[position])
		if !ok {
			return semanticInvalid()
		}
	}
	return nil
}

func (d *declarationIndex) resolveTarget(reference string, kinds []string) (declaration, bool) {
	count := 0
	var selected declaration
	for _, candidate := range d.aliases[reference] {
		if candidate.target {
			count++
			selected = candidate
		}
	}
	if count != 1 {
		return declaration{}, false
	}
	if len(kinds) == 0 {
		return selected, true
	}
	for _, kind := range kinds {
		prefix, wildcard := strings.CutSuffix(kind, ".*")
		if selected.kind == kind || wildcard && (selected.kind == prefix || strings.HasPrefix(selected.kind, prefix+".")) {
			return selected, true
		}
	}
	return declaration{}, false
}

func (d *declarationIndex) targetReferences(references []any) error {
	for _, reference := range references {
		if variable(reference) {
			continue
		}
		if _, ok := d.resolveTarget(text(reference), nil); !ok {
			return semanticInvalid()
		}
	}
	return nil
}

func (c materializedChecks) relationshipDatabase(relationship map[string]any) error {
	access := object(relationship[databaseAccessField])
	if access == nil {
		return nil
	}
	target, ok := c.index.resolveTarget(text(relationship[targetField]), []string{databaseServicesField, "database_services.databases"})
	if !ok { // An unresolved target is deferred by the endpoint check.
		return nil
	}
	return runtimeReference(text(access["role_ref"]), runtimeIDs(target.owner, "roles.*.role_id"))
}

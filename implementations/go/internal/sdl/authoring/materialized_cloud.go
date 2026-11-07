package authoring

import "github.com/OpenRAE/rae/implementations/go/internal/base/graph"

const (
	deploymentCellsField      = "deployment_cells"
	platformApplicationsField = "platform_applications"
	roleTerm                  = "role"

	cloudScopes   = "identity_authorities.resource_scopes"
	cloudSubjects = "identity_authorities.subjects"
	cloudPolicies = "identity_authorities.policies"
	cloudSecrets  = "platform_applications.secrets"
	cloudVersions = "platform_applications.secrets.versions"
)

type cloudChecks struct {
	root   materializedChecks
	scopes map[string]map[string]any
}

func (c materializedChecks) cloudResources() error {
	check := cloudChecks{root: c, scopes: map[string]map[string]any{}}
	for address := range c.index.addresses {
		entry := c.index.aliases[address][address]
		if entry.kind == cloudScopes {
			check.scopes[address] = entry.value
		}
	}
	if err := check.scopeGraph(); err != nil {
		return err
	}
	policies := map[string][]string{}
	for address := range c.index.addresses {
		entry := c.index.aliases[address][address]
		if err := check.item(address, entry); err != nil {
			return err
		}
		if entry.kind == cloudPolicies {
			ref := text(object(entry.value["resource_access"])["inherited_from_ref"])
			if c.index.aliases[ref][ref].kind == cloudPolicies {
				policies[address] = []string{ref}
			}
		}
	}
	if graph.HasCycle(policies) {
		return semanticInvalid()
	}
	return nil
}

func (c cloudChecks) model(reference, kind string) (declaration, error) {
	if variable(reference) {
		return declaration{}, nil
	}
	entry, ok := c.root.index.aliases[reference][reference]
	if !ok || entry.node == "" || entry.kind != kind {
		return declaration{}, semanticInvalid()
	}
	return entry, nil
}

func cloudResourceKind(kind string) bool {
	switch kind {
	case nodesSection, servicesField, infrastructureField, "acls", contentField, "content-item", accountsSection, identityDomainsField, identityForestsField, identityFacadesField, deploymentTenantsField, deploymentCellsField, persistentVolumesField, generatedArtifactsField, featuresSection, forwardingSection:
		return true
	default:
		return false
	}
}

func (c cloudChecks) resource(reference string, workload bool) error {
	if variable(reference) {
		return nil
	}
	entry, ok := c.root.index.aliases[reference][reference]
	if !ok || !cloudResourceKind(entry.kind) && entry.node == "" {
		return semanticInvalid()
	}
	if workload && !cloudWorkload(entry) {
		return semanticInvalid()
	}
	return nil
}

func cloudWorkload(entry declaration) bool {
	switch entry.kind {
	case servicesField, applicationsField, platformApplicationsField:
		return true
	case nodesSection:
		return text(entry.value["type"]) == computeType
	default:
		return false
	}
}

func (c cloudChecks) optionalScope(value map[string]any) error {
	ref := text(value["resource_scope_ref"])
	if ref != "" {
		_, err := c.model(ref, cloudScopes)
		return err
	}
	return nil
}

func (c cloudChecks) scopeGraph() error {
	edges := map[string][]string{}
	for address, scope := range c.scopes {
		ref := text(scope["parent_ref"])
		if ref == "" {
			continue
		}
		parent, err := c.model(ref, cloudScopes)
		if err != nil {
			return err
		}
		provider, parentProvider := text(scope["provider"]), text(parent.value["provider"])
		if parent.value != nil && !variable(provider) && !variable(parentProvider) && provider != parentProvider {
			return semanticInvalid()
		}
		if c.scopes[ref] != nil {
			edges[address] = []string{ref}
		}
	}
	if graph.HasCycle(edges) {
		return semanticInvalid()
	}
	return nil
}

func (c cloudChecks) item(address string, entry declaration) error {
	switch entry.kind {
	case cloudSubjects, platformApplicationsField, "platform_applications.cloud_limits":
		return c.optionalScope(entry.value)
	case "identity_authorities.identity_uses":
		return c.use(entry.value)
	case "identity_authorities.access_observations":
		return c.observation(entry.value)
	case cloudPolicies:
		return c.policy(object(entry.value["resource_access"]))
	case cloudSecrets:
		return c.secret(address, entry.value)
	case cloudVersions:
		return c.payload(text(entry.value["payload_content_ref"]))
	default:
		return nil
	}
}

func (c cloudChecks) use(value map[string]any) error {
	if err := c.resource(text(value["workload_ref"]), true); err != nil {
		return err
	}
	if _, err := c.model(text(value["principal_ref"]), cloudSubjects); err != nil {
		return err
	}
	if ref := text(value["source_principal_ref"]); ref != "" {
		_, err := c.model(ref, cloudSubjects)
		return err
	}
	return nil
}

func (c cloudChecks) observation(value map[string]any) error {
	if _, err := c.model(text(value["principal_ref"]), cloudSubjects); err != nil {
		return err
	}
	if err := c.resource(text(value["resource_ref"]), false); err != nil {
		return err
	}
	for _, reference := range array(value["context_refs"]) {
		if err := c.resource(text(reference), false); err != nil {
			return err
		}
	}
	return nil
}

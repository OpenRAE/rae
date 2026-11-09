package authoring

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

func cloudResourceKind(kind string) bool {
	switch kind {
	case nodesSection, servicesField, infrastructureField, "acls", contentField, "content-item", accountsSection, identityDomainsField, identityForestsField, identityFacadesField, deploymentTenantsField, deploymentCellsField, persistentVolumesField, generatedArtifactsField, featuresSection, forwardingSection:
		return true
	default:
		return false
	}
}

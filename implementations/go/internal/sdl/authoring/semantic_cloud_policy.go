package authoring

func (c *semanticCloud) policy(access *semanticCloudAccess) {
	c.resource(access.Attachment, "policy attachment reference", false)
	c.policySource(access)
	for _, binding := range access.Bindings {
		for _, ref := range binding.Principals {
			c.exactModel(ref, cloudSubjects, "policy principal reference")
		}
		for _, ref := range binding.Resources {
			c.resource(ref, "policy target reference", false)
		}
		if binding.Role != "" && c.exactModel(binding.Role, cloudSubjects, "policy role reference") {
			if role := c.subjects[binding.Role]; role != nil && role.Kind != roleTerm && !variable(role.Kind) {
				c.report("cloud-policy: role reference must name a role subject")
			}
		}
	}
}
func (c *semanticCloud) policySource(access *semanticCloudAccess) {
	if access.Source == "" || !c.exactModel(access.Source, cloudPolicies, "inherited policy reference") {
		return
	}
	source := c.policies[access.Source]
	if source == nil {
		return
	}
	if source.Access == nil {
		c.report("cloud-policy: an inherited policy source requires resource access meaning")
		return
	}
	c.inheritance(source.Access.Attachment, access.Attachment)
}
func (c *semanticCloud) inheritance(source, target string) {
	if variable(source) || variable(target) {
		return
	}
	if c.scopes[source] != nil {
		c.scopeInheritance(source, target)
		return
	}
	secret, version := c.secrets[source], c.versions[target]
	if secret == nil || version == nil || c.versionOwners[version] != secret {
		c.report("cloud-policy: inherited source must be a declared resource ancestry link")
	}
}
func (c *semanticCloud) scopeInheritance(source, target string) {
	sourceScope, targetScope := c.owningScope(source), c.owningScope(target)
	if variable(targetScope) {
		return
	}
	if sourceScope == "" || targetScope == "" {
		c.report("cloud-policy: inheritance requires declared source and target scopes")
		return
	}
	if source == target {
		c.report("cloud-policy: inherited source must be above its attachment in resource ancestry")
		return
	}
	if !c.scopeReaches(targetScope, sourceScope) {
		c.report("cloud-policy: inherited source must belong to declared target ancestry")
	}
}
func (c *semanticCloud) owningScope(ref string) string {
	if c.scopes[ref] != nil {
		return ref
	}
	if item := c.subjects[ref]; item != nil {
		return item.Scope
	}
	if item := c.secrets[ref]; item != nil {
		return item.Scope
	}
	if item := c.versions[ref]; item != nil {
		if owner := c.versionOwners[item]; owner != nil {
			return owner.Scope
		}
	}
	entry, known := c.model.index.declarations[ref]
	if known && entry.kind == platformApplicationsField {
		runtime, index := c.model.runtimeCollection(ref, platformApplicationsField)
		if runtime != nil && index < len(runtime.Platforms) {
			return runtime.Platforms[index].Scope
		}
	}
	return ""
}
func (c *semanticCloud) scopeReaches(current, source string) bool {
	seen := map[string]bool{}
	for !seen[current] {
		if current == source {
			return true
		}
		seen[current] = true
		scope := c.scopes[current]
		if scope == nil || scope.Parent == "" {
			return false
		}
		if variable(scope.Parent) {
			return true
		}
		current = scope.Parent
	}
	return false
}

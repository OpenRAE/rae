package authoring

func (c cloudChecks) policy(access map[string]any) error {
	if access == nil {
		return nil
	}
	if err := c.resource(text(access["attachment_ref"]), false); err != nil {
		return err
	}
	if sourceRef := text(access["inherited_from_ref"]); sourceRef != "" {
		if err := c.policySource(sourceRef, text(access["attachment_ref"])); err != nil {
			return err
		}
	}
	for _, binding := range array(access["bindings"]) {
		if err := c.binding(object(binding)); err != nil {
			return err
		}
	}
	return nil
}

func (c cloudChecks) policySource(reference, target string) error {
	source, err := c.model(reference, cloudPolicies)
	if err != nil {
		return err
	}
	if source.value == nil {
		return nil
	}
	inherited := object(source.value["resource_access"])
	if inherited == nil {
		return semanticInvalid()
	}
	return c.inheritance(text(inherited["attachment_ref"]), target)
}

func (c cloudChecks) binding(value map[string]any) error {
	for _, ref := range array(value["principal_refs"]) {
		if _, err := c.model(text(ref), cloudSubjects); err != nil {
			return err
		}
	}
	for _, ref := range array(value["resource_refs"]) {
		if err := c.resource(text(ref), false); err != nil {
			return err
		}
	}
	if ref := text(value["role_ref"]); ref != "" {
		role, err := c.model(ref, cloudSubjects)
		if err != nil {
			return err
		}
		kind := text(role.value["kind"])
		if role.value != nil && !variable(kind) && kind != roleTerm {
			return semanticInvalid()
		}
	}
	return nil
}

func (c cloudChecks) inheritance(sourceRef, targetRef string) error {
	if variable(sourceRef) || variable(targetRef) {
		return nil
	}
	if c.scopes[sourceRef] == nil {
		source := c.root.index.aliases[sourceRef][sourceRef]
		target := c.root.index.aliases[targetRef][targetRef]
		if source.kind != cloudSecrets || target.kind != cloudVersions || target.parent != sourceRef {
			return semanticInvalid()
		}
		return nil
	}
	if sourceRef == targetRef {
		return semanticInvalid()
	}
	targetScope := c.owningScope(targetRef)
	if variable(targetScope) {
		return nil
	}
	if targetScope == "" || !c.scopeReaches(targetScope, sourceRef) {
		return semanticInvalid()
	}
	return nil
}

func (c cloudChecks) owningScope(reference string) string {
	if c.scopes[reference] != nil {
		return reference
	}
	entry := c.root.index.aliases[reference][reference]
	if entry.kind == cloudVersions {
		entry = c.root.index.aliases[entry.parent][entry.parent]
	}
	return text(entry.value["resource_scope_ref"])
}

func (c cloudChecks) scopeReaches(current, source string) bool {
	seen := map[string]bool{}
	for !seen[current] {
		if current == source {
			return true
		}
		seen[current] = true
		parent := text(c.scopes[current]["parent_ref"])
		if parent == "" {
			return false
		}
		if variable(parent) {
			return true
		}
		current = parent
	}
	return false
}

package authoring

func (t *tenancyChecks) sharedService(relationship map[string]any) error {
	if text(relationship["type"]) != usesSharedServiceType || variable(relationship[sourceField]) || variable(relationship[targetField]) {
		return nil
	}
	tenant, ok := sectionRef(text(relationship[sourceField]), deploymentTenantsField, object(t.root.value[deploymentTenantsField]))
	node := t.root.namedServiceNode(text(relationship[targetField]))
	if !ok || node == "" {
		return semanticInvalid()
	}
	t.permissions[[2]string{tenant, text(relationship[targetField])}] = true
	detail := object(relationship[sharedServiceField])
	if err := sharedServicePolicy(detail, tenant != t.cellTenant[t.nodeCell[node]]); err != nil {
		return err
	}
	for _, ref := range array(detail["mutable_state_refs"]) {
		if variable(ref) {
			continue
		}
		if err := t.sharedServiceState(text(ref), tenant, node, text(detail["mutable_state_owner"])); err != nil {
			return err
		}
	}
	return nil
}

func sharedServicePolicy(detail map[string]any, crossTenant bool) error {
	isolation, authentication := text(detail["tenant_isolation"]), text(detail["workload_authentication"])
	owner, reset := text(detail["mutable_state_owner"]), text(detail["reset_generation_owner"])
	hasState := len(array(detail["mutable_state_refs"])) > 0
	if crossTenant && (isolation != "stateless" && isolation != "tenant_partitioned" || authentication != "tenant_scoped_workload_identity") {
		return semanticInvalid()
	}
	if isolation == "stateless" && owner == sharedServiceField || isolation == "tenant_partitioned" && (!hasState || owner != sharedServiceField || reset != sharedServiceField) {
		return semanticInvalid()
	}
	if hasState != (owner != "none") || reset != owner {
		return semanticInvalid()
	}
	return nil
}

func (t *tenancyChecks) sharedServiceState(reference, tenant, node, owner string) error {
	volumes := object(t.root.value[persistentVolumesField])
	name, ok := sectionRef(reference, persistentVolumesField, volumes)
	if !ok {
		return semanticInvalid()
	}
	identity := [2]string{tenant, owner}
	if previous, exists := t.stateOwners[name]; exists && previous != identity {
		return semanticInvalid()
	}
	t.stateOwners[name] = identity
	consumers := runtimeIDs(volumes[name], "consumers.*.node")
	if owner == "consumer_tenant" {
		if len(consumers) == 0 {
			return semanticInvalid()
		}
		for consumer := range consumers {
			if !t.tenantNodes[tenant][consumer] {
				return semanticInvalid()
			}
		}
	}
	if owner == sharedServiceField && !consumers[node] {
		return semanticInvalid()
	}
	return nil
}

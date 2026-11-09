package authoring

import "fmt"

type semanticSharedServiceContext struct {
	name, tenant, node, serviceTenant string
	detail                            semanticSharedService
}

func (t *semanticTenancy) sharedService(row semanticRelationship) {
	if row.kind != usesSharedServiceType || row.shared == nil || variable(row.source) || variable(row.target) {
		return
	}
	tenant, known := t.model.sectionReference(row.source, deploymentTenantsField)
	node := t.model.serviceNode(row.target)
	if !known || node == "" {
		t.collector.report(semanticOwner{relationshipsField, row.name}, fmt.Sprintf("Relationship '%s' must connect a deployment tenant to a named compute service", row.name))
		return
	}
	context := semanticSharedServiceContext{name: row.name, tenant: tenant, node: node, serviceTenant: t.cellTenant[t.nodeCell[node]], detail: *row.shared}
	for _, message := range sharedServiceIssues(context) {
		t.collector.report(semanticOwner{relationshipsField, row.name}, fmt.Sprintf("Relationship '%s' %s", row.name, message))
	}
	for _, ref := range row.shared.State {
		t.sharedState(ref, context)
	}
}
func sharedServiceIssues(context semanticSharedServiceContext) []string {
	row := context.detail
	var result []string
	if context.tenant != context.serviceTenant && (row.Isolation != "stateless" && row.Isolation != "tenant_partitioned" || row.Authentication != "tenant_scoped_workload_identity") {
		isolation := row.Isolation
		if isolation == "" {
			isolation = "cross-tenant"
		}
		result = append(result, isolation+" isolation requires tenant-scoped workload authentication")
	}
	return append(result, sharedStatePolicyIssues(row)...)
}
func sharedStatePolicyIssues(row semanticSharedService) []string {
	var result []string
	if row.Isolation == "stateless" && row.Owner == sharedServiceField {
		result = append(result, "stateless isolation forbids shared-service-owned mutable state")
	}
	if row.Isolation == "tenant_partitioned" && (len(row.State) == 0 || row.Owner != sharedServiceField || row.Reset != sharedServiceField) {
		result = append(result, "tenant_partitioned isolation requires shared-service-owned state and reset generation")
	}
	if len(row.State) > 0 && row.Owner == noneTerm {
		result = append(result, "mutable_state_refs require a non-none owner")
	}
	if len(row.State) == 0 && row.Owner != noneTerm {
		result = append(result, "mutable state owner requires mutable_state_refs")
	}
	if row.Owner != noneTerm && row.Reset != row.Owner {
		result = append(result, "reset_generation_owner must equal mutable state owner")
	}
	if row.Owner == noneTerm && row.Reset != noneTerm {
		result = append(result, "reset_generation_owner must be none without mutable state")
	}
	return result
}
func (t *semanticTenancy) sharedState(ref string, context semanticSharedServiceContext) {
	if variable(ref) {
		return
	}
	owner := semanticOwner{relationshipsField, context.name}
	name, known := t.model.sectionReference(ref, persistentVolumesField)
	if !known {
		t.collector.report(owner, fmt.Sprintf("Relationship '%s' mutable_state_ref '%s' does not resolve to a persistent volume", context.name, ref))
		return
	}
	identity := [2]string{context.tenant, context.detail.Owner}
	if previous, present := t.stateOwners[name]; present {
		if previous != identity {
			t.collector.report(semanticOwner{persistentVolumesField, name}, fmt.Sprintf("Persistent volume '%s' has conflicting shared-service owners", name))
		}
	} else {
		t.stateOwners[name] = identity
	}
	consumers := map[string]bool{}
	for _, consumer := range fieldValue(fieldValue(t.model.transport.PersistentVolumes)[name].Consumers) {
		consumers[fieldValue(consumer.Node)] = true
	}
	switch context.detail.Owner {
	case "consumer_tenant":
		if !tenantOwnsConsumers(consumers, t.tenantNodes[context.tenant]) {
			t.collector.report(owner, fmt.Sprintf("Relationship '%s' consumer-owned state must be consumed only by its tenant", context.name))
		}
	case sharedServiceField:
		if !consumers[context.node] {
			t.collector.report(owner, fmt.Sprintf("Relationship '%s' shared-service-owned state must be consumed by the service node", context.name))
		}
	}
}
func tenantOwnsConsumers(consumers, allowed map[string]bool) bool {
	if len(consumers) == 0 {
		return false
	}
	for node := range consumers {
		if !allowed[node] {
			return false
		}
	}
	return true
}
func (t *semanticTenancy) crossCellServices() {
	if len(t.nodeCell) == 0 {
		return
	}
	for _, row := range t.model.relationships {
		if row.kind != usesSharedServiceType || variable(row.source) || variable(row.target) {
			continue
		}
		tenant, known := t.model.sectionReference(row.source, deploymentTenantsField)
		if known && t.model.serviceNode(row.target) != "" {
			t.permissions[[2]string{tenant, row.target}] = true
		}
	}
	for _, row := range t.model.relationships {
		t.crossCellService(row)
	}
}
func (t *semanticTenancy) crossCellService(row semanticRelationship) {
	if row.kind == usesSharedServiceType || variable(row.source) || variable(row.target) {
		return
	}
	source, known := t.model.sectionReference(row.source, nodesSection)
	if !known {
		source = t.model.serviceNode(row.source)
	}
	target := t.model.serviceNode(row.target)
	left, right := t.nodeCell[source], t.nodeCell[target]
	if left == "" || right == "" || left == right {
		return
	}
	tenant := t.cellTenant[left]
	if tenant != "" && !t.permissions[[2]string{tenant, row.target}] {
		t.collector.report(semanticOwner{relationshipsField, row.name}, fmt.Sprintf("Relationship '%s' cross-cell service consumption requires an explicit shared-service binding for the consumer tenant and target service", row.name))
	}
}

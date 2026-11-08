package authoring

import "fmt"

type semanticSharedService struct {
	Isolation      string   `json:"tenant_isolation"`
	Authentication string   `json:"workload_authentication"`
	Owner          string   `json:"mutable_state_owner"`
	Reset          string   `json:"reset_generation_owner"`
	State          []string `json:"mutable_state_refs"`
}
type semanticTenancy struct {
	model                  *semanticModel
	collector              *semanticCollector
	nodeCell, cellTenant   map[string]string
	tenantNodes            map[string]map[string]bool
	carriers, carrierNames map[string]string
	carrierOrder           []string
	permissions            map[[2]string]bool
	stateOwners            map[string][2]string
}

func (m *semanticModel) checkTenancy(c *semanticCollector) {
	t := semanticTenancy{model: m, collector: c, nodeCell: map[string]string{}, cellTenant: map[string]string{}, tenantNodes: map[string]map[string]bool{}, carriers: map[string]string{}, carrierNames: map[string]string{}, permissions: map[[2]string]bool{}, stateOwners: map[string][2]string{}}
	t.cells()
	for _, row := range m.relationships {
		checkRelationshipDetails(c, row.name, row.kind, []semanticRelationshipDetail{{placedOnCarrierType, "carrier_placement", row.placement}, {usesSharedServiceType, sharedServiceField, row.shared != nil}})
	}
	for _, row := range m.relationships {
		t.placement(row)
	}
	t.placementGraph()
	for _, row := range m.relationships {
		t.sharedService(row)
	}
	t.crossCellServices()
}
func (t *semanticTenancy) cells() {
	values := fieldValue(t.model.transport.DeploymentCells)
	for _, name := range t.model.keys(deploymentCellsField) {
		row := values[name]
		tenant, ref := "", fieldValue(row.TenantRef)
		if !variable(ref) {
			var known bool
			tenant, known = t.model.sectionReference(ref, deploymentTenantsField)
			if !known {
				t.collector.report(semanticOwner{deploymentCellsField, name}, fmt.Sprintf("Deployment cell '%s' tenant_ref '%s' does not resolve to a deployment tenant", name, ref))
				tenant = ""
			} else {
				t.cellTenant[name] = tenant
			}
		}
		for _, node := range fieldValue(row.NodeRefs) {
			t.cellMember(name, tenant, node)
		}
	}
	if len(values) == 0 {
		return
	}
	for _, node := range t.model.nodes {
		if node.kind == computeType && t.nodeCell[node.name] == "" {
			t.collector.report(semanticOwner{nodesSection, node.name}, fmt.Sprintf("Compute node '%s' must belong to exactly one deployment cell", node.name))
		}
	}
}
func (t *semanticTenancy) cellMember(cell, tenant, ref string) {
	if variable(ref) {
		return
	}
	node, known := t.model.sectionReference(ref, nodesSection)
	if !known {
		t.collector.report(semanticOwner{deploymentCellsField, cell}, fmt.Sprintf("Deployment cell '%s' node_ref '%s' does not resolve to a node", cell, ref))
		return
	}
	if previous := t.nodeCell[node]; previous != "" && previous != cell {
		t.collector.report(semanticOwner{nodesSection, node}, fmt.Sprintf("Node '%s' belongs to multiple deployment cells: %s, %s", node, previous, cell))
		return
	}
	t.nodeCell[node] = cell
	if tenant != "" {
		if t.tenantNodes[tenant] == nil {
			t.tenantNodes[tenant] = map[string]bool{}
		}
		t.tenantNodes[tenant][node] = true
	}
}
func (t *semanticTenancy) placement(row semanticRelationship) {
	if row.kind != placedOnCarrierType || !row.placement || variable(row.source) || variable(row.target) {
		return
	}
	source, sourceOK := t.model.sectionReference(row.source, nodesSection)
	target, targetOK := t.model.sectionReference(row.target, nodesSection)
	owner := semanticOwner{relationshipsField, row.name}
	if !sourceOK || !targetOK || t.model.nodes[t.model.nodeIndex[source]].kind != computeType || t.model.nodes[t.model.nodeIndex[target]].kind != computeType {
		t.collector.report(owner, fmt.Sprintf("Relationship '%s' carrier placement endpoints must resolve to compute nodes", row.name))
		return
	}
	t.placementBindings(row.name, source, target)
	if _, present := t.carriers[source]; !present {
		t.carrierOrder = append(t.carrierOrder, source)
	}
	t.carriers[source], t.carrierNames[source] = target, row.name
}
func (t *semanticTenancy) placementBindings(name, source, target string) {
	owner := semanticOwner{relationshipsField, name}
	if source == target {
		t.collector.report(owner, fmt.Sprintf("Relationship '%s' cannot place a node on itself", name))
	}
	if previous := t.carriers[source]; previous != "" && previous != target {
		t.collector.report(semanticOwner{nodesSection, source}, fmt.Sprintf("Node '%s' has multiple carrier placements", source))
	}
	if t.model.nodes[t.model.nodeIndex[target]].persona != "carrier" {
		t.collector.report(owner, fmt.Sprintf("Relationship '%s' target '%s' must have endpoint persona 'carrier'", name, target))
	}
	left, right := t.nodeCell[source], t.nodeCell[target]
	if left != "" && right != "" && left != right {
		t.collector.report(owner, fmt.Sprintf("Relationship '%s' carrier placement crosses different deployment cells", name))
	}
}
func (t *semanticTenancy) placementGraph() {
	memo := map[string]bool{}
	for _, start := range t.carrierOrder {
		if t.placementCycle(start, memo) {
			name := t.carrierNames[start]
			t.collector.report(semanticOwner{relationshipsField, name}, fmt.Sprintf("Relationship '%s' participates in a carrier placement cycle", name))
		}
	}
	for _, source := range t.carrierOrder {
		if _, placed := t.carriers[t.carriers[source]]; placed {
			name := t.carrierNames[source]
			t.collector.report(semanticOwner{relationshipsField, name}, fmt.Sprintf("Relationship '%s' cannot place a node on another placed node", name))
		}
	}
}
func (t *semanticTenancy) placementCycle(start string, memo map[string]bool) bool {
	seen := map[string]bool{}
	var path []string
	current, result := start, false
	for {
		if cached, present := memo[current]; present {
			result = cached
			break
		}
		if seen[current] {
			result = true
			break
		}
		next, present := t.carriers[current]
		if !present {
			break
		}
		seen[current] = true
		path = append(path, current)
		current = next
	}
	for _, node := range path {
		memo[node] = result
	}
	return result
}

package authoring

const (
	placedOnCarrierType   = "placed_on_carrier"
	usesSharedServiceType = "uses_shared_service"
	sharedServiceField    = "shared_service"
)

type tenancyChecks struct {
	root        materializedChecks
	nodeCell    map[string]string
	cellTenant  map[string]string
	tenantNodes map[string]map[string]bool
	carriers    map[string]string
	permissions map[[2]string]bool
	stateOwners map[string][2]string
}

func (c materializedChecks) tenancy() error {
	t := tenancyChecks{root: c, nodeCell: map[string]string{}, cellTenant: map[string]string{}, tenantNodes: map[string]map[string]bool{}, carriers: map[string]string{}, permissions: map[[2]string]bool{}, stateOwners: map[string][2]string{}}
	if err := t.cells(); err != nil {
		return err
	}
	for _, raw := range object(c.value[relationshipsField]) {
		relationship := object(raw)
		if err := relationshipDetail(relationship, map[string]string{placedOnCarrierType: "carrier_placement", usesSharedServiceType: sharedServiceField}); err != nil {
			return err
		}
		if err := t.placement(relationship); err != nil {
			return err
		}
		if err := t.sharedService(relationship); err != nil {
			return err
		}
	}
	for _, target := range t.carriers {
		if _, nested := t.carriers[target]; nested {
			return semanticInvalid()
		}
	}
	return t.crossCellServices()
}

func (t *tenancyChecks) cells() error {
	cells, nodes := object(t.root.value[deploymentCellsField]), object(t.root.value[nodesSection])
	for name, raw := range cells {
		cell := object(raw)
		if err := t.cell(name, cell); err != nil {
			return err
		}
	}
	if len(cells) > 0 {
		for name, raw := range nodes {
			if text(object(raw)["type"]) == computeType && t.nodeCell[name] == "" {
				return semanticInvalid()
			}
		}
	}
	return nil
}

func (t *tenancyChecks) cell(name string, cell map[string]any) error {
	reference := text(cell["tenant_ref"])
	if !variable(reference) {
		tenant, ok := sectionRef(reference, deploymentTenantsField, object(t.root.value[deploymentTenantsField]))
		if !ok {
			return semanticInvalid()
		}
		t.cellTenant[name] = tenant
	}
	for _, ref := range array(cell["node_refs"]) {
		if variable(ref) {
			continue
		}
		node, ok := sectionRef(text(ref), nodesSection, object(t.root.value[nodesSection]))
		if !ok || t.nodeCell[node] != "" && t.nodeCell[node] != name {
			return semanticInvalid()
		}
		t.nodeCell[node] = name
		if tenant := t.cellTenant[name]; tenant != "" {
			if t.tenantNodes[tenant] == nil {
				t.tenantNodes[tenant] = map[string]bool{}
			}
			t.tenantNodes[tenant][node] = true
		}
	}
	return nil
}

func (t *tenancyChecks) placement(relationship map[string]any) error {
	if text(relationship["type"]) != placedOnCarrierType || variable(relationship[sourceField]) || variable(relationship[targetField]) {
		return nil
	}
	nodes := object(t.root.value[nodesSection])
	source, sourceOK := sectionRef(text(relationship[sourceField]), nodesSection, nodes)
	target, targetOK := sectionRef(text(relationship[targetField]), nodesSection, nodes)
	if !sourceOK || !targetOK || source == target || text(object(nodes[source])["type"]) != computeType || text(object(nodes[target])["type"]) != computeType || text(object(nodes[target])["endpoint_persona"]) != "carrier" {
		return semanticInvalid()
	}
	if previous := t.carriers[source]; previous != "" && previous != target {
		return semanticInvalid()
	}
	left, right := t.nodeCell[source], t.nodeCell[target]
	if left != "" && right != "" && left != right {
		return semanticInvalid()
	}
	t.carriers[source] = target
	return nil
}

func (c materializedChecks) namedServiceNode(reference string) string {
	for _, name := range c.nodeOrder {
		if c.serviceOwners[reference][name] {
			return name
		}
	}
	return ""
}

func (t *tenancyChecks) crossCellServices() error {
	for _, raw := range object(t.root.value[relationshipsField]) {
		relationship := object(raw)
		if text(relationship["type"]) == usesSharedServiceType || variable(relationship[sourceField]) || variable(relationship[targetField]) {
			continue
		}
		source, ok := sectionRef(text(relationship[sourceField]), nodesSection, object(t.root.value[nodesSection]))
		if !ok {
			source = t.root.namedServiceNode(text(relationship[sourceField]))
		}
		targetRef := text(relationship[targetField])
		target := t.root.namedServiceNode(targetRef)
		left, right := t.nodeCell[source], t.nodeCell[target]
		if tenant := t.cellTenant[left]; left != "" && right != "" && left != right && tenant != "" && !t.permissions[[2]string{tenant, targetRef}] {
			return semanticInvalid()
		}
	}
	return nil
}

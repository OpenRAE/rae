package authoring

import (
	"fmt"
	"math/big"
	"strings"
)

func (m *semanticModel) checkRuntimeNetwork(c *semanticCollector) {
	infrastructure := map[string]semanticInfrastructure{}
	for _, row := range m.infrastructure {
		infrastructure[row.name] = row
	}
	// Namespace ownership is one pass across nodes before endpoint checks.
	for _, node := range m.nodes {
		m.checkNetworkNamespace(c, node, infrastructure)
	}
	for _, node := range m.nodes {
		if node.runtime == nil || node.runtime.Network == nil {
			continue
		}
		for _, endpoint := range node.runtime.Network.Endpoints {
			m.checkRuntimeEndpoint(c, node.name, endpoint, infrastructure)
		}
	}
}
func (m *semanticModel) checkNetworkNamespace(c *semanticCollector, source semanticNode, infrastructure map[string]semanticInfrastructure) {
	namespace := source.runtime.networkNamespace()
	if namespace == nil || variable(namespace.Target) {
		return
	}
	name := strings.TrimPrefix(namespace.Target, nodesPrefix)
	target, known := m.node(name)
	owner, label := semanticOwner{nodesSection, source.name}, "Node '"+source.name+"'"
	if !known {
		c.report(owner, fmt.Sprintf("%s network namespace references undefined node '%s'", label, name))
		return
	}
	if source.name == name {
		c.report(owner, label+" cannot share its own network namespace")
		return
	}
	if target.kind != computeType {
		c.report(owner, fmt.Sprintf("%s network namespace target '%s' must reference a compute node", label, name))
	}
	if target.runtime.networkNamespace() != nil {
		c.report(owner, fmt.Sprintf("%s network namespace target '%s' must be a canonical namespace owner", label, name))
	}
	if !singletonInfrastructure(infrastructure[source.name]) || !singletonInfrastructure(infrastructure[name]) {
		c.report(owner, label+" network namespace sharing requires singleton source and target nodes")
	}
	m.checkSharedNamespaceState(c, source)
}
func singletonInfrastructure(entry semanticInfrastructure) bool {
	return entry.count == nil || entry.count.Cmp(big.NewInt(1)) == 0
}
func (m *semanticModel) checkSharedNamespaceState(c *semanticCollector, source semanticNode) {
	owner, label := semanticOwner{nodesSection, source.name}, "Node '"+source.name+"' sharing a network namespace cannot declare independent "
	entry := fieldValue(m.transport.Infrastructure)[source.name]
	if len(fieldValue(entry.Links)) > 0 || hasField(entry.Properties) || len(fieldValue(entry.Acls)) > 0 {
		c.report(owner, label+"infrastructure network state")
	}
	network := source.runtime.Network
	if network != nil && (len(network.Endpoints) > 0 || len(network.Published) > 0) {
		c.report(owner, label+"runtime network state")
	}
}
func (m *semanticModel) checkRuntimeEndpoint(c *semanticCollector, name string, endpoint semanticRuntimeEndpoint, infrastructure map[string]semanticInfrastructure) {
	ref := endpoint.Network
	if variable(ref) {
		return
	}
	owner, label := semanticOwner{nodesSection, name}, "Node '"+name+"' runtime network endpoint"
	entry, known := infrastructure[ref]
	if !known {
		c.report(owner, fmt.Sprintf("%s references undefined network '%s'", label, ref))
		return
	}
	if !m.isSwitch(ref) {
		c.report(owner, fmt.Sprintf("%s network '%s' must reference a switch/network entry", label, ref))
		return
	}
	if entry.network == nil {
		return
	}
	m.checkRuntimeEndpointAddresses(c, name, endpoint, entry.network.CIDR)
}
func (m *semanticModel) checkRuntimeEndpointAddresses(c *semanticCollector, name string, endpoint semanticRuntimeEndpoint, cidr string) {
	if cidr == "" || variable(cidr) {
		return
	}
	network, err := networkPrefix(cidr)
	if err != nil {
		return
	}
	for _, field := range []struct{ name, value string }{{"ip_address", endpoint.Address}, {"gateway", endpoint.Gateway}} {
		if field.value == "" || variable(field.value) {
			continue
		}
		address, addressErr := networkAddress(field.value)
		if addressErr == nil && address.BitLen() == network.Addr().BitLen() && !network.Contains(address.WithZone("")) {
			c.report(semanticOwner{nodesSection, name}, fmt.Sprintf("Node '%s' runtime network endpoint %s %s is not within network '%s' CIDR %s", name, field.name, field.value, endpoint.Network, cidr))
		}
	}
}

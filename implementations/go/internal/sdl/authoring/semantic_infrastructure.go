package authoring

import (
	"encoding/json"
	"fmt"
	"math/big"
	"slices"
	"strconv"
)

type semanticInfrastructure struct {
	name                string
	links, dependencies []string
	count               *big.Int
	network             *semanticNetwork
	assignments         []semanticIPAssignment
	acls                []semanticACL
}
type semanticNetwork struct {
	CIDR string `json:"cidr"`
}
type semanticIPAssignment struct{ network, address string }
type semanticACL struct {
	From string `json:"from_net"`
	To   string `json:"to_net"`
}

func (m *semanticModel) infrastructureFacts() error {
	for _, name := range m.keys(infrastructureField) {
		entry, err := m.infrastructureFact(name)
		if err != nil {
			return err
		}
		m.infrastructure = append(m.infrastructure, entry)
	}
	return nil
}
func (m *semanticModel) infrastructureFact(name string) (semanticInfrastructure, error) {
	raw := fieldValue(m.transport.Infrastructure)[name]
	entry := semanticInfrastructure{name: name, links: fieldValue(raw.Links), dependencies: fieldValue(raw.Dependencies)}
	if count := fieldValue(raw.Count); len(count) != 0 {
		entry.count, _ = modelInteger(json.Number(count))
	}
	for _, acl := range fieldValue(raw.Acls) {
		entry.acls = append(entry.acls, semanticACL{fieldValue(acl.FromNet), fieldValue(acl.ToNet)})
	}
	if err := m.infrastructureProperties(&entry, fieldValue(raw.Properties)); err != nil {
		return semanticInfrastructure{}, err
	}
	return entry, nil
}
func (m *semanticModel) infrastructureProperties(entry *semanticInfrastructure, raw json.RawMessage) error {
	if len(raw) == 0 {
		return nil
	}
	switch raw[0] {
	case '{':
		entry.network = &semanticNetwork{}
		if err := json.Unmarshal(raw, entry.network); err != nil {
			return invalid()
		}
	case '[':
		var assignments []map[string]string
		if err := json.Unmarshal(raw, &assignments); err != nil {
			return invalid()
		}
		for i, assignment := range assignments {
			for _, network := range m.keys(infrastructureField, entry.name, "properties", strconv.Itoa(i)) {
				entry.assignments = append(entry.assignments, semanticIPAssignment{network, assignment[network]})
			}
		}
	}
	return nil
}

func (m *semanticModel) node(name string) (semanticNode, bool) {
	index, present := m.nodeIndex[name]
	if !present {
		return semanticNode{}, false
	}
	return m.nodes[index], true
}
func (m *semanticModel) isSwitch(name string) bool {
	node, present := m.node(name)
	return present && node.kind == switchType
}

func (m *semanticModel) checkInfrastructure(c *semanticCollector) {
	entries := map[string]semanticInfrastructure{}
	for _, entry := range m.infrastructure {
		entries[entry.name] = entry
	}
	for _, entry := range m.infrastructure {
		if _, exists := m.node(entry.name); !exists {
			c.report(semanticOwner{infrastructureField, entry.name}, fmt.Sprintf("Infrastructure '%s' does not match any defined node", entry.name))
		}
		m.checkInfrastructureLinks(c, entry, entries)
		m.checkInfrastructureCount(c, entry)
		for _, assignment := range entry.assignments {
			m.checkInfrastructureIP(c, entry, assignment, entries)
		}
		m.checkInfrastructureACLs(c, entry, entries)
	}
}
func (m *semanticModel) checkInfrastructureLinks(c *semanticCollector, entry semanticInfrastructure, entries map[string]semanticInfrastructure) {
	owner := semanticOwner{infrastructureField, entry.name}
	for _, reference := range entry.links {
		if variable(reference) {
			continue
		}
		if _, exists := entries[reference]; !exists {
			c.report(owner, fmt.Sprintf("Infrastructure '%s' links to undefined '%s'", entry.name, reference))
		} else if !m.isSwitch(reference) {
			c.report(owner, fmt.Sprintf("Infrastructure '%s' link '%s' must reference a switch/network entry", entry.name, reference))
		}
	}
	for _, reference := range entry.dependencies {
		if _, exists := entries[reference]; !exists && !variable(reference) {
			c.report(owner, fmt.Sprintf("Infrastructure '%s' depends on undefined '%s'", entry.name, reference))
		}
	}
}
func (m *semanticModel) checkInfrastructureCount(c *semanticCollector, entry semanticInfrastructure) {
	node, exists := m.node(entry.name)
	if !exists || entry.count == nil || entry.count.Cmp(big.NewInt(1)) <= 0 {
		return
	}
	owner := semanticOwner{nodesSection, node.name}
	if node.kind == switchType {
		c.report(owner, fmt.Sprintf("Switch node '%s' cannot have count > 1", node.name))
	}
	hasConditions := slices.ContainsFunc(node.bindings, func(ref semanticBinding) bool { return ref.section == conditionsSection })
	if node.kind == computeType && hasConditions {
		c.report(owner, fmt.Sprintf("Node '%s' has conditions and cannot have count > 1", node.name))
	}
}
func (m *semanticModel) checkInfrastructureACLs(c *semanticCollector, entry semanticInfrastructure, entries map[string]semanticInfrastructure) {
	owner := semanticOwner{infrastructureField, entry.name}
	for _, acl := range entry.acls {
		for _, reference := range []string{acl.From, acl.To} {
			if reference == "" || variable(reference) {
				continue
			}
			if _, exists := entries[reference]; !exists {
				c.report(owner, fmt.Sprintf("Infrastructure '%s' ACL references undefined network '%s'", entry.name, reference))
			} else if !m.isSwitch(reference) {
				c.report(owner, fmt.Sprintf("Infrastructure '%s' ACL reference '%s' must point to a switch/network entry", entry.name, reference))
			}
		}
	}
}

func (m *semanticModel) checkInfrastructureIP(c *semanticCollector, entry semanticInfrastructure, assignment semanticIPAssignment, entries map[string]semanticInfrastructure) {
	link, ip := assignment.network, assignment.address
	if variable(link) {
		return
	}
	owner := semanticOwner{infrastructureField, entry.name}
	if !slices.Contains(entry.links, link) {
		c.report(owner, fmt.Sprintf("Infrastructure '%s' property references unlinked node '%s'", entry.name, link))
	}
	if !m.isSwitch(link) {
		c.report(owner, fmt.Sprintf("Infrastructure '%s' property link '%s' must reference a switch/network entry", entry.name, link))
		return
	}
	linked, present := entries[link]
	if !present || linked.network == nil {
		if present {
			c.report(owner, fmt.Sprintf("Infrastructure '%s' property link '%s' must reference a network with CIDR properties", entry.name, link))
		}
		return
	}
	cidr := linked.network.CIDR
	if variable(ip) || variable(cidr) {
		return
	}
	network, err := networkPrefix(cidr)
	if err != nil {
		c.report(semanticOwner{infrastructureField, link}, fmt.Sprintf("Infrastructure '%s' has invalid CIDR %s", link, cidr))
		return
	}
	address, err := networkAddress(ip)
	if err != nil {
		c.report(owner, fmt.Sprintf("Infrastructure '%s' has invalid IP assignment '%s' for link '%s'", entry.name, ip, link))
		return
	}
	if !network.Contains(address.WithZone("")) {
		c.report(owner, fmt.Sprintf("Infrastructure '%s' IP %s not within '%s' CIDR %s", entry.name, ip, link, cidr))
	}
}

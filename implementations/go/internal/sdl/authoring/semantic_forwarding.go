package authoring

import (
	"fmt"
	"slices"
	"strings"
)

type semanticForwardTarget struct {
	ID       string  `json:"target_id"`
	Node     string  `json:"target_node_ref"`
	Service  string  `json:"target_service_ref"`
	Protocol *string `json:"protocol"`
}

func (t semanticForwardTarget) protocol() string {
	if t.Protocol == nil {
		return unknownTerm
	}
	return *t.Protocol
}
func (m *semanticModel) checkRuntimeForwarding(c *semanticCollector) {
	locations := map[string][]string{}
	var order []string
	for _, agent := range m.forwarders {
		if agent.ID == "" {
			continue
		}
		if len(locations[agent.ID]) == 0 {
			order = append(order, agent.ID)
		}
		location := "scenario forwarding_agents"
		if agent.node != "" {
			location = fmt.Sprintf("node '%s' runtime.forwarding_agents", agent.node)
		}
		locations[agent.ID] = append(locations[agent.ID], location)
	}
	for _, id := range order {
		if len(locations[id]) > 1 {
			c.report(semanticOwner{}, fmt.Sprintf("Duplicate forwarding_agent_id '%s' across %s", id, strings.Join(locations[id], ", ")))
		}
	}
	for _, agent := range m.forwarders {
		m.forwardingTargets(c, agent)
	}
}
func (m *semanticModel) forwardingTargets(c *semanticCollector, agent semanticForwarder) {
	owner, label := agent.owner, fmt.Sprintf("Scenario forwarding agent '%s'", agent.ID)
	if agent.node != "" {
		owner = semanticOwner{nodesSection, agent.node}
		label = fmt.Sprintf("Node '%s' runtime forwarding agent '%s'", agent.node, agent.ID)
	}
	for _, target := range agent.Targets {
		m.forwardingTarget(c, owner, label+" ship_target '"+target.ID+"'", agent.node, target)
	}
}
func (m *semanticModel) forwardingTarget(c *semanticCollector, owner semanticOwner, label, local string, target semanticForwardTarget) {
	node := local
	if concreteReference(target.Node) {
		if !m.definitions[nodesSection][target.Node] {
			c.report(owner, fmt.Sprintf("%s target_node_ref '%s' does not resolve to a defined node", label, target.Node))
			return
		}
		node = target.Node
	}
	if !concreteReference(target.Service) {
		return
	}
	if local == "" {
		if target.Node == "" {
			c.report(owner, fmt.Sprintf("%s target_service_ref '%s' requires target_node_ref because scenario-level forwarding agents have no owning node", label, target.Service))
			return
		}
		if variable(target.Node) {
			return
		}
	}
	if index, present := m.nodeIndex[node]; present && !slices.Contains(m.nodes[index].services, target.Service) {
		c.report(owner, fmt.Sprintf("%s target_service_ref '%s' does not resolve to a service on node '%s'", label, target.Service, node))
	}
}

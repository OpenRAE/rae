package authoring

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"
)

type semanticAgent struct {
	name, role                                                            string
	affiliations, starting, subnets, anchors, scopes, actions, boundaries []string
	knowledge                                                             *semanticKnowledge
	accesses                                                              []semanticAccess
}
type semanticKnowledge struct {
	Hosts    []string `json:"hosts"`
	Subnets  []string `json:"subnets"`
	Services []string `json:"services"`
	Accounts []string `json:"accounts"`
}

func (m *semanticModel) agentFacts() error {
	values := fieldValue(m.transport.Agents)
	for _, name := range m.keys(agentsSection) {
		raw := values[name]
		row := semanticAgent{name: name, affiliations: fieldValue(raw.Affiliations), starting: fieldValue(raw.StartingAccounts), subnets: fieldValue(raw.AllowedSubnets), anchors: fieldValue(raw.AuthorityAnchors), scopes: fieldValue(raw.OperatingScope), actions: fieldValue(raw.Actions), boundaries: fieldValue(raw.ObservationBoundaries)}
		var err error
		row.role, err = scalarText(fieldValue(raw.Role), "")
		if err != nil {
			return err
		}
		row.accesses, err = m.accessFacts(name)
		if err != nil {
			return err
		}
		if raw.InitialKnowledge.Present() && !raw.InitialKnowledge.Null() {
			if err := json.Unmarshal(fieldValue(raw.InitialKnowledge), &row.knowledge); err != nil {
				return invalid()
			}
		}
		m.agents = append(m.agents, row)
	}
	return nil
}
func (m *semanticModel) checkAgents(c *semanticCollector) {
	m.checkAffiliations(c)
	services := map[string]bool{}
	for _, node := range m.nodes {
		for _, name := range node.services {
			if name != "" {
				services[name] = true
			}
		}
	}
	for _, row := range m.agents {
		owner, label := semanticOwner{agentsSection, row.name}, "Agent '"+row.name+"'"
		m.agentMembership(c, owner, label, "starting_account", row.starting, accountsSection)
		m.agentSubnets(c, owner, label, "allowed_subnet", row.subnets)
		if row.knowledge != nil {
			m.agentKnowledge(c, owner, label, *row.knowledge, services)
		}
		for _, ref := range row.anchors {
			m.namedReference(c, owner, label, "authority_anchor", ref, referenceAuthorityAnchor)
		}
		for _, ref := range row.scopes {
			m.checkOperatingScope(c, owner, label, ref)
		}
	}
}
func (m *semanticModel) checkAffiliations(c *semanticCollector) {
	for _, row := range m.agents {
		seen := map[string]bool{}
		for _, ref := range row.affiliations {
			if variable(ref) {
				continue
			}
			switch {
			case !m.entityNames[ref]:
				c.report(semanticOwner{agentsSection, row.name}, fmt.Sprintf("Agent '%s' affiliation references undefined entity '%s'", row.name, ref))
			case seen[ref]:
				c.report(semanticOwner{agentsSection, row.name}, fmt.Sprintf("Agent '%s' affiliations must name distinct entities", row.name))
			}
			seen[ref] = true
		}
	}
}
func (m *semanticModel) agentMembership(c *semanticCollector, owner semanticOwner, label, field string, refs []string, section string) {
	for _, ref := range refs {
		if !variable(ref) && !m.definitions[section][ref] {
			c.report(owner, fmt.Sprintf("%s %s '%s' not in %s section", label, field, ref, section))
		}
	}
}
func (m *semanticModel) agentSubnets(c *semanticCollector, owner semanticOwner, label, field string, refs []string) {
	for _, ref := range refs {
		if variable(ref) {
			continue
		}
		switch {
		case !m.definitions[infrastructureField][ref]:
			c.report(owner, fmt.Sprintf("%s %s '%s' not in infrastructure section", label, field, ref))
		case !m.isSwitch(ref):
			c.report(owner, fmt.Sprintf("%s %s '%s' must reference a switch/network entry", label, field, ref))
		}
	}
}
func (m *semanticModel) agentKnowledge(c *semanticCollector, owner semanticOwner, label string, knowledge semanticKnowledge, services map[string]bool) {
	for _, ref := range knowledge.Hosts {
		if variable(ref) {
			continue
		}
		node, known := m.node(ref)
		switch {
		case !known:
			c.report(owner, fmt.Sprintf("%s initial_knowledge host '%s' not in nodes section", label, ref))
		case node.kind != computeType:
			c.report(owner, fmt.Sprintf("%s initial_knowledge host '%s' must reference a compute node", label, ref))
		}
	}
	m.agentSubnets(c, owner, label, "initial_knowledge subnet", knowledge.Subnets)
	for _, ref := range knowledge.Services {
		if !variable(ref) && !services[ref] {
			c.report(owner, fmt.Sprintf("%s initial_knowledge service '%s' not in node service names", label, ref))
		}
	}
	m.agentMembership(c, owner, label, "initial_knowledge account", knowledge.Accounts, accountsSection)
}
func (m *semanticModel) checkOperatingScope(c *semanticCollector, owner semanticOwner, label, ref string) {
	if variable(ref) {
		return
	}
	candidates := m.operating.aliases[ref]
	if len(candidates) == 0 {
		c.report(owner, fmt.Sprintf("%s operating_scope '%s' does not reference any defined targetable element", label, ref))
		return
	}
	if len(candidates) > 1 {
		var names []string
		for address := range candidates {
			names = append(names, address)
		}
		slices.Sort(names)
		c.report(owner, fmt.Sprintf("%s operating_scope '%s' is ambiguous; use one of: %s", label, ref, strings.Join(names, ", ")))
	}
}
